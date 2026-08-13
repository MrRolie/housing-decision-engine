# demoflow Tranche 1 Implementation Plan

> **For agentic workers:** Implement this plan task-by-task, in order. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/specs/2026-07-21-demoflow-demographic-scenario-module-design.md` — the why/intent lives here; read it before executing.

**Goal:** Build Tranche 1 of the demoflow module — fail-loud data loaders + typed junctions + live probes (T1a), the household cohort roll-forward with competing-risk decrements and calibration gates (T1b), and coarse demand netting → excess-demand fractions → geography rankings → tripwire baselines → committed golden artifacts (T1c) — as a self-contained uv project.

**Architecture:** `demoflow/` is its OWN uv project inside the repo (own `pyproject.toml`, lockfile, venv, tests), sibling to `src/hde/` + `mcp_server/`. It takes a uv **path dependency on `../../actuarial-system`** for the CPM2014/CPM-B mortality engine (`mcp_server.engine.mortality`) and installs actuarial-system's `mcp_server` package — it NEVER installs hde's distribution. The two envs are never shared: hde's repo also ships a top-level `mcp_server`, so co-installation would collide; isolation is by construction, not discipline. Coupling to hde is the future ScenarioPrior artifact file only (Tranche 2).

**Tech Stack:** Python ≥3.12, uv, pandas + openpyxl, pytest; actuarial-system (CPM2014_combined / CPM-B via `mcp_server.engine.mortality`).

**Execution precondition:** PR #4 (S4a) merged; execute from post-merge `main` in a worktree. The demoflow spec + committed ISQ workbooks (`docs/research/2026-07-21-demographic-housing-flow-grounding/data/`) ride that merge.

**Not a money-moving change** (personal decision tooling) — but **load-bearing / decision-critical**: the spec's load-bearing-claim tag ("fail-loud loaders, no silent fallback"; the tripwire fail-safe gate) plus the demand/balance math make this audit-worthy. So **three pre-PR adversarial audit tasks ARE injected** — Task 31 (quant-financial-engineer), Task 32 (stress-tester), Task 33 (data-integrity-validator) — run after T1c, before the PR. `stress-tester` runs BOTH as Task 32 (pre-PR, findings foldable into the branch) AND again at PR time via the external review hook. The executor sets audit discipline off THIS line: audit tasks are present, not deferred.

**Session boundaries** (sub-lettered tasks 8b/15b/25b were inserted while folding codex rounds 1–6):
- **T1a — Tasks 0–16 (incl. 8b, 15b)** (scaffold + probes + loader-validation contracts + loaders + junctions + per-sex living-arrangement + import-direction contract)
- **T1b — Tasks 17–24** (basis guard + three-bucket per-sex cohort init + competing-risk algebra + calibration gates + 100+ absorbing bucket + transfer/market split)
- **T1c — Tasks 25–30 (incl. 25b)** (native-formation + dimensional immigrant chain + I2 gate + OwnerStock eq + excess-demand + rankings + tripwires + golden artifacts + CLI)

**Folded to codex round 9 (FINAL — loop paused)** (spec git `ba9be3d`, sha256 `c5ec0cc…`): rounds 1–6 as before PLUS r7–9 — §4 ratio nonneg carve-out + signed-flow carve-out; §5 reconciliation composition pinned + oracle-exact mutation; §6 native a_min=18 (no wraparound) + P_resident≥0 per cell + HORS_RMR literal row/three-way flows; §7 OwnerStock<1000 guard + identity envelope + typed rank_stable + run-contract central values + projected-year domain + general no-open-string validator; §7c source-bound-to-registry + UNKNOWN-branch nullability; §8 'Territoire hors des RMR'→HORS_RMR.

**Import-direction contract (holds for every task):** a task's test imports ONLY symbols defined in that task or an earlier one. `demoflow` never imports `hde` or hde's `mcp_server`; it MAY import `mcp_server.engine.mortality` — that resolves to **actuarial-system's** `mcp_server`, the only one in demoflow's env. Error classes are flat: `LoaderError(Exception)`, `CalibrationError(Exception)`, `BasisError(Exception)` — following hde's sole precedent `ConfigValidationError(Exception)` (`src/hde/config.py:27`).

**Pinned external seams (verified live 2026-07-21 while writing this plan — do not re-derive):**
- `mcp_server.engine.mortality.set_active_mortality(base_table: str, scale: str) -> None`
- `mcp_server.engine.mortality.active_mortality() -> tuple[str, str]` (module default is US `("RP2014_combined","MP2021")`)
- `mcp_server.engine.mortality.get_qx(age: int, gender: str, calendar_year: int) -> float` — `gender` MUST be `"M"` or `"F"` (raises `ValueError` else); `age` clamped to `[0,120]`, returns `1.0` at 120.
- Oracle q_x (calendar 2035, CPM2014_combined+CPM-B): M75=0.0156, F75=0.0115, M85=0.0596, F85=0.0426, M95=0.2367, F95=0.1803, M100=0.3534, F100=0.3049.
- ISQ `pop-as-*` sheet `"Années d'âge"`; two-row header at 0-indexed rows **6,7**. NOTE: the loader deliberately reads with `header=None` and forward-fills the level-0 group row (Task 10) — the naïve `pandas header=[6,7]` form is REJECTED because duplicate `'100+'` column names defeat header-group selection. Junction columns `Scénario, Code, Région1, Année, Statut, Sexe` then grouped-age + single-year `Âge` blocks.
- ISQ `compo-*` single sheet `"Scénarios de 2026"`; deep header rows 5–9; `"Immigrants permanents"` at 0-indexed column **16** (group `"Migration internationale"`), `"Solde des résidents non permanents"` at column **18**; data from Excel row 11.
- sha256 of committed workbooks (from `docs/research/2026-07-21-demographic-housing-flow-grounding/data/`):
  - `pop-as-rmr-base.xlsx` `288d8c9f03d05ece6ae1271e2cf55226a534d4fe27005ca76fb2ef305f0882d7`
  - `pop-as-ra-base.xlsx` `ae9de62fd8631668e127e5cd37ec10028959a38a18831e1c5e4d102a1c8779fe`
  - `pop-as-qc-base.xlsx` `1d286d252a75195db6ab66ac767e352d9f74e4e2359c68eba4a43301c9c61fd4`
  - `compo-rmr-base.xlsx` `096246df47a95f729d46bacdb655cf297f4779163d62ee25e95254b5cc23844b`
  - `compo-ra-base.xlsx` `1b81a82b0f0588a3217eb93b74d37044addf08934731dfd612e846e6de7b728f`
- ISQ re-download slug pattern (fallback only, undocumented — pin + checksum + fail-loud on drift): `https://statistique.quebec.ca/fr/fichier/<slug>.xlsx` where `<slug>` ∈ {`pop-as-rmr-base`, `pop-as-ra-base`, `pop-as-qc-base`, `compo-rmr-base`, `compo-ra-base`}.

**Every command runs from `demoflow/` unless stated. Conventional commits: `feat(demoflow): …` / `test(demoflow): …`.**

---

## T1a — Loaders, junctions, probes (Tasks 0–16)

### Task 0: Scaffold the uv project + flat error classes + committed data

**Files:**
- Create: `demoflow/pyproject.toml`
- Create: `demoflow/src/demoflow/__init__.py`
- Create: `demoflow/src/demoflow/errors.py`
- Create: `demoflow/data/` (copy the 5 committed workbooks into it)
- Create: `demoflow/probes/.gitkeep`
- Create: `demoflow/tests/__init__.py`
- Test: `demoflow/tests/test_scaffold.py`

- [ ] **Step 1: Create the uv project files**

`demoflow/pyproject.toml`:
```toml
[project]
name = "demoflow"
version = "0.0.1"
description = "Demographic housing-flow scenario module (Québec RMR): fail-loud loaders, cohort roll-forward, excess-demand rankings, tripwires."
requires-python = ">=3.12"
dependencies = [
    "pandas>=2.0",
    "openpyxl>=3.1",
    "actuarial-system",
]

[project.optional-dependencies]
dev = ["pytest>=7.0"]

[project.scripts]
demoflow = "demoflow.cli:main"

[tool.uv.sources]
actuarial-system = { path = "../../actuarial-system" }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/demoflow"]
```

`demoflow/src/demoflow/errors.py`:
```python
"""Flat error taxonomy for demoflow. Follows hde's sole precedent
(ConfigValidationError(Exception), src/hde/config.py:27): no hierarchy
unless the degenerate taxonomy genuinely forces one."""


class LoaderError(Exception):
    """Raised when a data source drifts from its pinned contract
    (404 / size / checksum / schema / degenerate cell) — never impute,
    never warn-and-continue."""


class CalibrationError(Exception):
    """Raised when a cohort roll-forward violates a calibration gate
    (reconciliation band, q out of [0,1])."""


class BasisError(Exception):
    """Raised when the active mortality basis is not the Québec basis
    before a get_qx call. Explicit if-check, never a bare assert."""
```

`demoflow/src/demoflow/__init__.py`:
```python
"""demoflow — demographic housing-flow scenario module (Tranche 1)."""

from demoflow.errors import BasisError, CalibrationError, LoaderError

__all__ = ["LoaderError", "CalibrationError", "BasisError"]
```

`demoflow/tests/__init__.py`: (empty file)

`demoflow/probes/.gitkeep`: (empty file — keeps the recorded-observation dir tracked)

- [ ] **Step 2: Copy the committed workbooks into demoflow/data/**

Run (from repo root):
```bash
mkdir -p demoflow/data
cp docs/research/2026-07-21-demographic-housing-flow-grounding/data/*.xlsx demoflow/data/
ls -la demoflow/data/
```
Expected: 5 `.xlsx` files present (~8.4MB total). These are the demoflow project's own committed SoT copies (spec §3); identical bytes → identical sha256 to the docs/research vintage (pinned in Task 8).

- [ ] **Step 3: Write the scaffold smoke test**

`demoflow/tests/test_scaffold.py`:
```python
from pathlib import Path

import demoflow
from demoflow.errors import BasisError, CalibrationError, LoaderError

DATA = Path(__file__).resolve().parent.parent / "data"


def test_error_classes_are_flat_exceptions():
    for cls in (LoaderError, CalibrationError, BasisError):
        assert issubclass(cls, Exception)
        assert cls.__bases__ == (Exception,)


def test_public_api_reexports_errors():
    assert demoflow.LoaderError is LoaderError


def test_committed_workbooks_present():
    names = {p.name for p in DATA.glob("*.xlsx")}
    assert names == {
        "pop-as-rmr-base.xlsx", "pop-as-ra-base.xlsx", "pop-as-qc-base.xlsx",
        "compo-rmr-base.xlsx", "compo-ra-base.xlsx",
    }
```

- [ ] **Step 4: Sync the env and run the test**

Run:
```bash
cd demoflow && uv sync --extra dev
cd demoflow && uv run pytest tests/test_scaffold.py -v
```
Expected: cross-env install of actuarial-system succeeds; 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/pyproject.toml demoflow/uv.lock demoflow/src demoflow/data demoflow/probes demoflow/tests
git commit -m "feat(demoflow): scaffold uv project + flat error classes + committed ISQ workbooks"
```

---

### Task 1 (Probe P1): Cross-env actuarial import + q_x oracle

**Files:**
- Create: `demoflow/probes/run_p1.py`
- Create (by running): `demoflow/probes/P1-actuarial-cross-env.md`
- Test: `demoflow/tests/test_probe_p1.py`

- [ ] **Step 1: Write the probe script**

`demoflow/probes/run_p1.py`:
```python
"""P1 — cross-env actuarial import. Runs live, records an observation note.
Sets the Québec basis and pulls q_x(75, M/F, 2035); compares to skeleton spot
values (M75=0.0156, F75=0.0115)."""
from pathlib import Path

from mcp_server.engine.mortality import active_mortality, get_qx, set_active_mortality

OUT = Path(__file__).resolve().parent / "P1-actuarial-cross-env.md"


def main() -> None:
    set_active_mortality("CPM2014_combined", "CPM-B")
    base, scale = active_mortality()
    m75 = get_qx(75, "M", 2035)
    f75 = get_qx(75, "F", 2035)
    m100 = get_qx(100, "M", 2035)
    lines = [
        "# P1 — Cross-env actuarial import (RECORDED OBSERVATION)",
        "",
        f"- active_mortality() after set = ({base!r}, {scale!r})",
        f"- get_qx(75,'M',2035) = {m75:.4f}  (skeleton oracle 0.0156)",
        f"- get_qx(75,'F',2035) = {f75:.4f}  (skeleton oracle 0.0115)",
        f"- get_qx(100,'M',2035) = {m100:.4f} (100+ cap resolves; skeleton 0.3534)",
        "- VERDICT: cross-env get_qx fires with QC basis." ,
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the probe live and record**

Run:
```bash
cd demoflow && uv run python probes/run_p1.py
```
Expected: writes `probes/P1-actuarial-cross-env.md`; basis echoes `('CPM2014_combined','CPM-B')`; M75≈0.0156, F75≈0.0115. If import fails or basis does not echo → record the failure verbatim in the note and STOP (this is the first live boundary; a failure here blocks T1b).

- [ ] **Step 3: Write the oracle assertion test**

`demoflow/tests/test_probe_p1.py`:
```python
from pathlib import Path

import pytest
from mcp_server.engine.mortality import active_mortality, get_qx, set_active_mortality

NOTE = Path(__file__).resolve().parent.parent / "probes" / "P1-actuarial-cross-env.md"


def test_p1_observation_recorded():
    assert NOTE.exists(), "run probes/run_p1.py first"


def test_qc_basis_qx_matches_skeleton_oracle():
    set_active_mortality("CPM2014_combined", "CPM-B")
    assert active_mortality() == ("CPM2014_combined", "CPM-B")
    assert get_qx(75, "M", 2035) == pytest.approx(0.0156, abs=5e-4)
    assert get_qx(75, "F", 2035) == pytest.approx(0.0115, abs=5e-4)


def test_get_qx_rejects_bad_gender():
    set_active_mortality("CPM2014_combined", "CPM-B")
    with pytest.raises(ValueError):
        get_qx(75, "male", 2035)
```

- [ ] **Step 4: Run the test**

Run: `cd demoflow && uv run pytest tests/test_probe_p1.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/probes/run_p1.py demoflow/probes/P1-actuarial-cross-env.md demoflow/tests/test_probe_p1.py
git commit -m "test(demoflow): P1 probe — cross-env actuarial import + q_x oracle recorded"
```

---

### Task 2 (Probe P2): StatCan WDS pull of 98-10-0231-01 (MTL + QC CMA + QC province)

**Files:**
- Create: `demoflow/probes/run_p2.py`
- Create (by running): `demoflow/probes/P2-census-tenure-age.md`, `demoflow/data/census_tenure_age_98100231.csv` (raw pulled table, committed if the pull succeeds)
- Test: `demoflow/tests/test_probe_p2.py`

- [ ] **Step 1: Write the probe script**

`demoflow/probes/run_p2.py`:
```python
"""P2 — StatCan WDS table pull for 98-10-0231-01 (tenure x age of primary
maintainer). Pull the FULL table via the WDS getFullTableDownloadCSV endpoint
(productId 98100231). Record MTL CMA, QC CMA, AND the Québec-province total
(HORS_RMR derives as province-net-of-CMAs, codex F8). The fragile FOGS
alternative.cfm chart-page path is FORBIDDEN in code."""
import io
import zipfile
from pathlib import Path

import pandas as pd
import urllib.request

WDS = "https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/98100231/en"
OUT_NOTE = Path(__file__).resolve().parent / "P2-census-tenure-age.md"
OUT_CSV = Path(__file__).resolve().parent.parent / "data" / "census_tenure_age_98100231.csv"


def main() -> None:
    note = ["# P2 — StatCan 98-10-0231-01 tenure x age (RECORDED OBSERVATION)", ""]
    try:
        meta = pd.read_json(WDS)  # {"status","object": <zip url>}
        zip_url = meta.loc["object", 0] if 0 in meta.columns else meta["object"].iloc[0]
        note.append(f"- WDS endpoint: {WDS}")
        note.append(f"- resolved zip url: {zip_url}")
        raw = urllib.request.urlopen(zip_url, timeout=120).read()
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            csv_name = [n for n in zf.namelist() if n.endswith(".csv") and "MetaData" not in n][0]
            df = pd.read_csv(io.BytesIO(zf.read(csv_name)), dtype=str)
        df.to_csv(OUT_CSV, index=False)
        geo_col = [c for c in df.columns if "GEO" in c.upper()][0]
        geos = sorted(df[geo_col].dropna().unique())
        note += [
            f"- columns: {list(df.columns)}",
            f"- geo column: {geo_col}",
            f"- distinct GEO count: {len(geos)}; sample: {geos[:12]}",
            "- Pull: 'Quebec' province total AND EVERY QC CMA the table carries (Montréal, Québec,",
            "  Ottawa-Gatineau QC-part, Saguenay, Sherbrooke, Trois-Rivières, Drummondville).",
            "- HORS_RMR = province tenure NET of ALL QC CMAs (codex r4-F2 — NOT just MTL+QC).",
            "- CA CAVEAT (codex r5-F7): a published 'non-CMA/CA' row EXCLUDES Census Agglomerations",
            "  while province-minus-CMAs INCLUDES them — use the published row ONLY if it reconciles",
            "  exactly (numerators AND denominators) against the computed residual; else COMPUTE the",
            "  residual and RECORD which geography HORS_RMR actually denotes.",
            "- Oracle to confirm downstream: 56.2% owner, 75+, Montréal CMA.",
            "- VERDICT: WIRED (table pulled + committed).",
        ]
    except Exception as exc:  # record failure + spec fallback, never silent
        note += [
            f"- LIVE PULL FAILED: {type(exc).__name__}: {exc}",
            "- FALLBACK (spec §4): ownership rate is a hard input; without this table",
            "  the ownership loader (Task 13) cannot join — record the failure and retry",
            "  the WDS endpoint / productId before proceeding. NO silent substitute.",
        ]
    OUT_NOTE.write_text("\n".join(note) + "\n")
    print("\n".join(note))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the probe live and record**

Run:
```bash
cd demoflow && uv run python probes/run_p2.py
```
Expected: writes `probes/P2-census-tenure-age.md` and (on success) `data/census_tenure_age_98100231.csv`. The note records the true column set and confirms MTL CMA + QC CMA + Québec province rows exist. On failure it records the exact error and the no-silent-substitute rule.

- [ ] **Step 3: Write the assertion test**

`demoflow/tests/test_probe_p2.py`:
```python
from pathlib import Path

NOTE = Path(__file__).resolve().parent.parent / "probes" / "P2-census-tenure-age.md"


def test_p2_observation_recorded():
    assert NOTE.exists(), "run probes/run_p2.py first"
    text = NOTE.read_text()
    # The note must state a VERDICT — either WIRED or an explicit recorded failure.
    assert ("VERDICT: WIRED" in text) or ("LIVE PULL FAILED" in text)
```

- [ ] **Step 4: Run the test**

Run: `cd demoflow && uv run pytest tests/test_probe_p2.py -v`
Expected: 1 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/probes/run_p2.py demoflow/probes/P2-census-tenure-age.md demoflow/tests/test_probe_p2.py
# add the CSV only if the pull succeeded:
git add demoflow/data/census_tenure_age_98100231.csv 2>/dev/null || true
git commit -m "test(demoflow): P2 probe — StatCan WDS tenure-by-age table recorded"
```

---

### Task 3 (Probe P3): Census living-arrangement cross-tab hunt

**Files:**
- Create: `demoflow/probes/run_p3.py`
- Create (by running): `demoflow/probes/P3-living-arrangement.md`
- Test: `demoflow/tests/test_probe_p3.py`

- [ ] **Step 1: Write the probe script**

`demoflow/probes/run_p3.py`:
```python
"""P3 — hunt a Census living-arrangement cross-tab (household type x age of
maintainer, CMA level) via the WDS. If not free at CMA granularity, record
NOT-FOUND and the spec fallback: ISQ vitrine 28% living-alone (65+, QC-wide)
with a widened band [24%, 34%] and a `borrowed_prior` flag."""
import json
import urllib.request
from pathlib import Path

# Candidate WDS cubes to probe (household type / living arrangements x age of maintainer).
CANDIDATES = ["98100134", "98100026", "98100040"]
OUT = Path(__file__).resolve().parent / "P3-living-arrangement.md"
WDS = "https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata"  # POST [{"productId": int}]


def main() -> None:
    note = ["# P3 — Census living-arrangement cross-tab hunt (RECORDED OBSERVATION)", ""]
    for pid in CANDIDATES:
        try:
            body = json.dumps([{"productId": int(pid)}]).encode()
            req = urllib.request.Request(WDS, data=body, headers={"Content-Type": "application/json"})
            payload = json.loads(urllib.request.urlopen(req, timeout=60).read())
            obj = payload[0].get("object", {}) if isinstance(payload, list) and payload else {}
            dims = [d.get("dimensionNameEn") for d in obj.get("dimension", [])]
            note.append(f"- {pid}: dimensions = {dims}  (need household type x age of maintainer x SEX at CMA)")
        except Exception as exc:
            note.append(f"- {pid}: probe error {type(exc).__name__}: {exc}")
    note += [
        "",
        "## DECISION — SEX-SPECIFIC rates required (living_alone AND couple_share by age x sex; r3-F1/r4-F1)",
        "- FOUND at CMA granularity (household type x age x SEX)?  [FILL: yes/no]",
        "- PER-INPUT fallbacks (codex r4-F6 — the living-alone fallback CANNOT supply couple_share):",
        "  * living_alone -> vitrine 28% (65+, QC), widened band [0.24, 0.34] PER-SEX, `borrowed_prior`",
        "    (constants `living_alone_vitrine`; the living-arrangement loader applies it per sex).",
        "  * couple_share -> pinned at probe time from the Census PROVINCE-LEVEL profile WITH CITATION",
        "    (recorded here); calibrate per-sex so coupled_m ~= coupled_f on the real populations.",
        "- If NEITHER the cross-tab NOR a citable couple_share exists -> initialization RAISES",
        "  (LoaderError). couple_share has NO invented default (spec §11.3).  [FILL: couple_share source + citation]",
    ]
    OUT.write_text("\n".join(note) + "\n")
    print("\n".join(note))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the probe live and record**

Run: `cd demoflow && uv run python probes/run_p3.py`
Expected: writes `probes/P3-living-arrangement.md`. The executor confirms found/not-found at CMA
granularity, fills the DECISION block, and records the SEX-SPECIFIC per-input fallbacks — the
living_alone vitrine band (per-sex, `borrowed_prior`) AND a couple_share province-level citation
(or the initialization raises). The committed `living_arrangement.json` (Task 15b) carries these.

- [ ] **Step 3: Write the assertion test**

`demoflow/tests/test_probe_p3.py`:
```python
from pathlib import Path

NOTE = Path(__file__).resolve().parent.parent / "probes" / "P3-living-arrangement.md"


def test_p3_records_sex_specific_fallbacks():
    assert NOTE.exists(), "run probes/run_p3.py first"
    text = NOTE.read_text()
    assert "SEX-SPECIFIC" in text and "0.24" in text and "0.34" in text
    assert "borrowed_prior" in text
    assert "couple_share" in text and "no invented default" in text.lower()
```

- [ ] **Step 4: Run the test**

Run: `cd demoflow && uv run pytest tests/test_probe_p3.py -v`
Expected: 1 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/probes/run_p3.py demoflow/probes/P3-living-arrangement.md demoflow/tests/test_probe_p3.py
git commit -m "test(demoflow): P3 probe — living-arrangement hunt + vitrine fallback recorded"
```

---

### Task 4 (Probe P4): Census immigrant vs non-immigrant ownership by CMA

**Files:**
- Create: `demoflow/probes/run_p4.py`
- Create (by running): `demoflow/probes/P4-immigrant-ownership-diff.md`
- Test: `demoflow/tests/test_probe_p4.py`

- [ ] **Step 1: Write the probe script**

`demoflow/probes/run_p4.py`:
```python
"""P4 — Census immigrant vs non-immigrant homeownership differential by CMA.
This is the Tranche-1 COARSE-NETTING multiplier (spec §6): the immigrant-arrival
stock uses the immigrant/non-immigrant ownership differential, applied as a
banded multiplier. Census-covered for Québec (unlike ROC-CHSP). Record the
differential for the Montréal + Québec CMAs and the band."""
from pathlib import Path

import pandas as pd

# Immigrant status x tenure x CMA (2021 Census). Probe the WDS product.
WDS = "https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/98100279/en"
OUT = Path(__file__).resolve().parent / "P4-immigrant-ownership-diff.md"


def main() -> None:
    note = ["# P4 — Immigrant vs non-immigrant ownership differential (RECORDED)", ""]
    try:
        meta = pd.read_json(WDS)
        obj = meta["object"].iloc[0] if "object" in meta.columns else meta.loc["object", 0]
        note += [
            f"- WDS endpoint: {WDS}",
            f"- resolved object: {obj}",
            "- FILL from the table: owner_rate(immigrant, MTL CMA), owner_rate(non-immigrant, MTL CMA),",
            "  and the differential = immigrant / non-immigrant (a <1.0 multiplier if immigrants own less).",
            "- Repeat for Québec CMA.",
            "- Encode as a BANDED multiplier (point +/- spread) in constants (Task 15).",
            "- VERDICT: WIRED.",
        ]
    except Exception as exc:
        note += [
            f"- LIVE PULL FAILED: {type(exc).__name__}: {exc}",
            "- FALLBACK: retry alternate immigrant-status-x-tenure product id; the coarse",
            "  netting is load-bearing (spec §6) — record a documented multiplier band with",
            "  `borrowed_prior` if the exact CMA cell is unavailable. NO silent 1.0.",
        ]
    OUT.write_text("\n".join(note) + "\n")
    print("\n".join(note))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the probe live and record**

Run: `cd demoflow && uv run python probes/run_p4.py`
Expected: writes `probes/P4-immigrant-ownership-diff.md` with the differential (immigrant/non-immigrant owner rate) for MTL + QC CMAs, encoded as a banded multiplier, or a recorded failure + documented fallback band (never a silent 1.0 — that would collapse the netting).

- [ ] **Step 3: Write the assertion test**

`demoflow/tests/test_probe_p4.py`:
```python
from pathlib import Path

NOTE = Path(__file__).resolve().parent.parent / "probes" / "P4-immigrant-ownership-diff.md"


def test_p4_records_differential_or_failure():
    assert NOTE.exists(), "run probes/run_p4.py first"
    text = NOTE.read_text()
    assert ("VERDICT: WIRED" in text) or ("LIVE PULL FAILED" in text)
    assert "multiplier" in text.lower()
```

- [ ] **Step 4: Run the test**

Run: `cd demoflow && uv run pytest tests/test_probe_p4.py -v`
Expected: 1 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/probes/run_p4.py demoflow/probes/P4-immigrant-ownership-diff.md demoflow/tests/test_probe_p4.py
git commit -m "test(demoflow): P4 probe — immigrant ownership differential recorded"
```

---

### Task 5 (Probe P5): IRCC PR admissions by CMA CSV

**Files:**
- Create: `demoflow/probes/run_p5.py`
- Create (by running): `demoflow/probes/P5-ircc-pr-by-cma.md`
- Test: `demoflow/tests/test_probe_p5.py`

- [ ] **Step 1: Write the probe script**

`demoflow/probes/run_p5.py`:
```python
"""P5 — IRCC permanent-resident admissions by CMA + category (open.canada.ca
monthly CSV). Used by the tripwire (realized PR landings vs MIFI plan), NOT by
the demand model (that uses ISQ compo 'Immigrants permanents'). Record schema +
the suppressed-<5 cell convention (handled as a 0-band)."""
from pathlib import Path

import pandas as pd

# open.canada.ca package: IRCC monthly PR updates by CMA. Probe the CKAN API.
CKAN = ("https://open.canada.ca/data/api/3/action/package_search"
        "?q=permanent+residents+census+metropolitan+area+monthly")
OUT = Path(__file__).resolve().parent / "P5-ircc-pr-by-cma.md"


def main() -> None:
    note = ["# P5 — IRCC PR admissions by CMA (RECORDED OBSERVATION)", ""]
    try:
        pkg = pd.read_json(CKAN)
        note += [
            f"- CKAN search: {CKAN}",
            "- FILL: the matching package id + the CSV resource url.",
            "- FILL: columns (expect CMA, month/year, category, count).",
            "- Suppressed cells (<5) -> treat as 0-band (spec §4).",
            "- VERDICT: located.",
        ]
    except Exception as exc:
        note += [
            f"- LIVE SEARCH FAILED: {type(exc).__name__}: {exc}",
            "- FALLBACK: until wired, the PR-landings tripwire reports UNKNOWN (never a",
            "  stale within-band). Record the failure.",
        ]
    OUT.write_text("\n".join(note) + "\n")
    print("\n".join(note))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the probe live and record**

Run: `cd demoflow && uv run python probes/run_p5.py`
Expected: writes `probes/P5-ircc-pr-by-cma.md` with the package id, CSV resource URL, columns, and the suppressed-<5 convention — or a recorded failure with the UNKNOWN-tripwire fallback.

- [ ] **Step 3: Write the assertion test**

`demoflow/tests/test_probe_p5.py`:
```python
from pathlib import Path

NOTE = Path(__file__).resolve().parent.parent / "probes" / "P5-ircc-pr-by-cma.md"


def test_p5_records_schema_or_failure():
    assert NOTE.exists(), "run probes/run_p5.py first"
    text = NOTE.read_text()
    assert ("VERDICT: located" in text) or ("LIVE SEARCH FAILED" in text)
```

- [ ] **Step 4: Run the test**

Run: `cd demoflow && uv run pytest tests/test_probe_p5.py -v`
Expected: 1 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/probes/run_p5.py demoflow/probes/P5-ircc-pr-by-cma.md demoflow/tests/test_probe_p5.py
git commit -m "test(demoflow): P5 probe — IRCC PR-by-CMA schema recorded"
```

---

### Task 6 (Probe P5b): Temporary-resident stock source pick

**Files:**
- Create: `demoflow/probes/run_p5b.py`
- Create (by running): `demoflow/probes/P5b-temp-resident-stock.md`
- Test: `demoflow/tests/test_probe_p5b.py`

- [ ] **Step 1: Write the probe script**

`demoflow/probes/run_p5b.py`:
```python
"""P5b — pick the temporary-resident STOCK source (codex F5): StatCan NPR
estimates (17-10-0121-01 family) vs IRCC temporary-resident tables. Record the
choice + schema + cadence. Note: ISQ compo already carries 'Solde des residents
non permanents' (net NPR flow, column 18) — record whether that suffices or a
stock series is needed. Until wired, the tripwire reports UNKNOWN."""
from pathlib import Path

import pandas as pd

NPR_WDS = "https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/17100121/en"
OUT = Path(__file__).resolve().parent / "P5b-temp-resident-stock.md"


def main() -> None:
    note = ["# P5b — Temporary-resident STOCK source pick (RECORDED)", ""]
    try:
        meta = pd.read_json(NPR_WDS)
        obj = meta["object"].iloc[0] if "object" in meta.columns else meta.loc["object", 0]
        note += [
            f"- StatCan NPR 17-10-0121 WDS: {NPR_WDS} -> {obj}",
            "- FILL: does 17100121 carry a QUARTERLY NPR stock by province/CMA? cadence?",
            "- ALT: ISQ compo col 18 'Solde des residents non permanents' (annual net flow).",
            "- CHOICE: [FILL: NPR-stock | compo-net-flow | IRCC-TR-tables] + why.",
            "- VERDICT: source chosen.",
        ]
    except Exception as exc:
        note += [
            f"- LIVE PULL FAILED: {type(exc).__name__}: {exc}",
            "- FALLBACK: tripwire reports UNKNOWN for temp-resident stock until wired.",
        ]
    OUT.write_text("\n".join(note) + "\n")
    print("\n".join(note))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the probe live and record**

Run: `cd demoflow && uv run python probes/run_p5b.py`
Expected: writes `probes/P5b-temp-resident-stock.md` recording the chosen source (NPR stock vs compo net-flow vs IRCC TR), schema, and cadence — or a failure + UNKNOWN-tripwire fallback.

- [ ] **Step 3: Write the assertion test**

`demoflow/tests/test_probe_p5b.py`:
```python
from pathlib import Path

NOTE = Path(__file__).resolve().parent.parent / "probes" / "P5b-temp-resident-stock.md"


def test_p5b_records_choice_or_failure():
    assert NOTE.exists(), "run probes/run_p5b.py first"
    text = NOTE.read_text()
    assert ("VERDICT: source chosen" in text) or ("LIVE PULL FAILED" in text)
```

- [ ] **Step 4: Run the test**

Run: `cd demoflow && uv run pytest tests/test_probe_p5b.py -v`
Expected: 1 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/probes/run_p5b.py demoflow/probes/P5b-temp-resident-stock.md demoflow/tests/test_probe_p5b.py
git commit -m "test(demoflow): P5b probe — temporary-resident stock source chosen"
```

---

### Task 7 (Probe P6): MRC-level ISQ source hunt

**Files:**
- Create: `demoflow/probes/run_p6.py`
- Create (by running): `demoflow/probes/P6-mrc-isq-hunt.md`
- Test: `demoflow/tests/test_probe_p6.py`

- [ ] **Step 1: Write the probe script**

`demoflow/probes/run_p6.py`:
```python
"""P6 — hunt an MRC-level ISQ projection source for couronne-nord precision.
The RMR slug convention 404'd for MRC (spec §8). Try product pages / full-edition
downloads. v0 PROCEEDS REGARDLESS — a find only enables a v1 Geography-enum
extension, never a v0 change."""
from pathlib import Path

import urllib.request

CANDIDATES = [
    "https://statistique.quebec.ca/fr/fichier/pop-as-mrc-base.xlsx",
    "https://statistique.quebec.ca/fr/fichier/pop-mrc-base.xlsx",
]
OUT = Path(__file__).resolve().parent / "P6-mrc-isq-hunt.md"


def main() -> None:
    note = ["# P6 — MRC-level ISQ source hunt (RECORDED OBSERVATION)", ""]
    for url in CANDIDATES:
        try:
            req = urllib.request.Request(url, method="HEAD")
            resp = urllib.request.urlopen(req, timeout=30)
            note.append(f"- {url}: HTTP {resp.status} (size {resp.headers.get('Content-Length')})")
        except Exception as exc:
            note.append(f"- {url}: {type(exc).__name__}: {exc}")
    note += [
        "",
        "## DECISION",
        "- MRC workbook found?  [FILL: yes/no]",
        "- v0 PROCEEDS REGARDLESS. If found -> v1 Geography-enum extension (couronne-nord),",
        "  NOT a v0 change. RA14/15/16 proxies carry `ra_proxy` in v0 (spec §8).",
    ]
    OUT.write_text("\n".join(note) + "\n")
    print("\n".join(note))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the probe live and record**

Run: `cd demoflow && uv run python probes/run_p6.py`
Expected: writes `probes/P6-mrc-isq-hunt.md` recording HEAD results (likely 404) and the "v0 proceeds regardless" decision.

- [ ] **Step 3: Write the assertion test**

`demoflow/tests/test_probe_p6.py`:
```python
from pathlib import Path

NOTE = Path(__file__).resolve().parent.parent / "probes" / "P6-mrc-isq-hunt.md"


def test_p6_records_hunt_and_v0_proceeds():
    assert NOTE.exists(), "run probes/run_p6.py first"
    assert "v0 PROCEEDS REGARDLESS" in NOTE.read_text()
```

- [ ] **Step 4: Run the test**

Run: `cd demoflow && uv run pytest tests/test_probe_p6.py -v`
Expected: 1 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/probes/run_p6.py demoflow/probes/P6-mrc-isq-hunt.md demoflow/tests/test_probe_p6.py
git commit -m "test(demoflow): P6 probe — MRC-level ISQ hunt recorded (v0 proceeds)"
```

---

### Task 8: sha256 pins module + verification

**Files:**
- Create: `demoflow/src/demoflow/loaders/__init__.py`
- Create: `demoflow/src/demoflow/loaders/pins.py`
- Test: `demoflow/tests/test_pins.py`

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_pins.py`:
```python
import hashlib
from pathlib import Path

import pytest

from demoflow.loaders.pins import DATA_DIR, WORKBOOK_SHA256, verify_pin
from demoflow.errors import LoaderError


def test_committed_workbooks_match_pins():
    for name, expected in WORKBOOK_SHA256.items():
        digest = hashlib.sha256((DATA_DIR / name).read_bytes()).hexdigest()
        assert digest == expected, f"{name} drifted: {digest} != {expected}"


def test_verify_pin_raises_on_drift(tmp_path):
    bad = tmp_path / "pop-as-rmr-base.xlsx"
    bad.write_bytes(b"not the workbook")
    with pytest.raises(LoaderError, match="sha256"):
        verify_pin(bad, "pop-as-rmr-base.xlsx")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_pins.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.loaders.pins`).

- [ ] **Step 3: Write the implementation**

`demoflow/src/demoflow/loaders/__init__.py`: (empty file)

`demoflow/src/demoflow/loaders/pins.py`:
```python
"""sha256 pins for the committed ISQ workbooks. The loader loads from a
configurable path defaulting to demoflow/data/; a pinned re-download (spec §4
slug URLs) is a FALLBACK only, and any drift (404/size/checksum) raises
LoaderError."""
import hashlib
from pathlib import Path

from demoflow.errors import LoaderError

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"

WORKBOOK_SHA256 = {
    "pop-as-rmr-base.xlsx": "288d8c9f03d05ece6ae1271e2cf55226a534d4fe27005ca76fb2ef305f0882d7",
    "pop-as-ra-base.xlsx": "ae9de62fd8631668e127e5cd37ec10028959a38a18831e1c5e4d102a1c8779fe",
    "pop-as-qc-base.xlsx": "1d286d252a75195db6ab66ac767e352d9f74e4e2359c68eba4a43301c9c61fd4",
    "compo-rmr-base.xlsx": "096246df47a95f729d46bacdb655cf297f4779163d62ee25e95254b5cc23844b",
    "compo-ra-base.xlsx": "1b81a82b0f0588a3217eb93b74d37044addf08934731dfd612e846e6de7b728f",
}

ISQ_SLUG_URL = "https://statistique.quebec.ca/fr/fichier/{slug}.xlsx"


def verify_pin(path: Path, name: str) -> None:
    """Raise LoaderError if `path` does not match the pinned sha256 for `name`."""
    expected = WORKBOOK_SHA256.get(name)
    if expected is None:
        raise LoaderError(f"no sha256 pin registered for {name!r}")
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if digest != expected:
        raise LoaderError(f"sha256 drift for {name}: expected {expected}, got {digest}")
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_pins.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/loaders/__init__.py demoflow/src/demoflow/loaders/pins.py demoflow/tests/test_pins.py
git commit -m "feat(demoflow): sha256 pins + fail-loud drift check for ISQ workbooks"
```

---

### Task 8b: Loader validation contracts (fraction / finite / primary-key / year-lattice)

**Files:**
- Create: `demoflow/src/demoflow/loaders/validate.py`
- Test: `demoflow/tests/test_validate.py`

Folded spec §4 (codex r4-F3, r5-F1/F2, r6-F3): every FRACTION input ∈[0,1]; every numeric input
FINITE (NaN/±Inf raise); every loaded series declares its PRIMARY KEY (duplicates raise); the year
lattice is CONTIGUOUS **and pinned to the expected endpoints (2021–2051)** AND has an IDENTICAL
year domain across every geography×scenario×sex series (a missing terminal year for one geography
raises — no silently shortened ranking mean). One shared module so every loader enforces it.

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_validate.py`:
```python
import math

import pandas as pd
import pytest

from demoflow.loaders.validate import (
    assert_fraction, assert_finite, assert_nonneg_finite, assert_unique_primary_key,
    assert_year_lattice, assert_uniform_year_domain, assert_statut_sublattice,
)
from demoflow.errors import LoaderError


def test_fraction_accepts_unit_interval_rejects_out_of_range_and_nonfinite():
    assert assert_fraction("x", 0.0) == 0.0
    assert assert_fraction("x", 1.0) == 1.0
    for bad in (1.0000001, -1e-9, math.nan, math.inf, -math.inf):
        with pytest.raises(LoaderError):
            assert_fraction("x", bad)


def test_nonneg_finite_ratio_carveout_allows_gt_one():
    assert assert_nonneg_finite("ratio", 1.2) == 1.2   # ratio can exceed 1 (not a fraction)
    assert assert_nonneg_finite("ratio", 0.0) == 0.0
    for bad in (-0.01, math.nan, math.inf):
        with pytest.raises(LoaderError):
            assert_nonneg_finite("ratio", bad)


def test_finite_rejects_nan_inf_and_nonnumeric():
    assert assert_finite("x", 5.0) == 5.0
    for bad in (math.nan, math.inf, -math.inf, "n/a", None):
        with pytest.raises(LoaderError):
            assert_finite("x", bad)


def test_primary_key_uniqueness():
    ok = pd.DataFrame({"g": [1, 1], "y": [2030, 2031], "v": [1.0, 2.0]})
    assert_unique_primary_key(ok, ["g", "y"], "pop")  # no raise
    dup = pd.DataFrame({"g": [1, 1], "y": [2030, 2030], "v": [1.0, 2.0]})
    with pytest.raises(LoaderError, match="duplicate"):
        assert_unique_primary_key(dup, ["g", "y"], "pop")


def test_year_lattice_contiguity_and_expected_span():
    assert_year_lattice([2030, 2031, 2032], "pop")                      # contiguous, no span check
    with pytest.raises(LoaderError, match="contiguous|lattice"):
        assert_year_lattice([2030, 2031, 2033], "pop")                  # 2032 deleted
    with pytest.raises(LoaderError, match="empty"):
        assert_year_lattice([], "pop")
    assert_year_lattice(list(range(2021, 2052)), "pop", expected_span=(2021, 2051))  # ok
    with pytest.raises(LoaderError, match="span|endpoint"):
        assert_year_lattice(list(range(2021, 2051)), "pop", expected_span=(2021, 2051))  # 2051 missing


def test_uniform_year_domain_across_series():
    ok = pd.DataFrame({"geo": ["A", "A", "B", "B"], "sex": ["M"] * 4,
                       "year": [2030, 2031, 2030, 2031], "v": [1.0, 2.0, 3.0, 4.0]})
    assert_uniform_year_domain(ok, ["geo", "sex"], "year", "pop")       # every series {2030,2031}
    bad = pd.DataFrame({"geo": ["A", "A", "B"], "sex": ["M"] * 3,
                        "year": [2030, 2031, 2030], "v": [1.0, 2.0, 3.0]})  # B missing 2031
    with pytest.raises(LoaderError, match="domain|terminal"):
        assert_uniform_year_domain(bad, ["geo", "sex"], "year", "pop")


def test_statut_sublattice_single_transition_and_uniform_projected_domain():
    ok = pd.DataFrame({"geo": ["A"] * 4 + ["B"] * 4, "year": [2021, 2022, 2023, 2024] * 2,
                       "status": ["est", "est", "proj", "proj"] * 2})
    assert_statut_sublattice(ok, ["geo"], "year", "status", {"est", "proj"}, "pop")   # no raise
    # RED: relabel B's terminal 2024 proj->est (raw lattice intact; projected domain shortens)
    bad = ok.copy()
    bad.loc[(bad["geo"] == "B") & (bad["year"] == 2024), "status"] = "est"
    with pytest.raises(LoaderError, match="reversal|transitions|PROJECTED-year domain"):
        assert_statut_sublattice(bad, ["geo"], "year", "status", {"est", "proj"}, "pop")
    with pytest.raises(LoaderError, match="allowed set"):
        assert_statut_sublattice(ok.assign(status="???"), ["geo"], "year", "status", {"est", "proj"}, "pop")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_validate.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.loaders.validate`).

- [ ] **Step 3: Write the implementation**

`demoflow/src/demoflow/loaders/validate.py`:
```python
"""Shared loader validation contracts (spec §4). Fail-loud, never impute."""
import math

import pandas as pd

from demoflow.errors import LoaderError


def assert_finite(name: str, value) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        raise LoaderError(f"{name}: non-numeric value {value!r}")
    if not math.isfinite(f):
        raise LoaderError(f"{name}: non-finite value {value!r}")
    return f


def assert_fraction(name: str, value) -> float:
    f = assert_finite(name, value)
    if not 0.0 <= f <= 1.0:
        raise LoaderError(f"{name}: fraction outside [0,1]: {f}")
    return f


def assert_nonneg_finite(name: str, value) -> float:
    """Nonnegative-finite (codex r7-F8 ratio carve-out): the immigrant/non-immigrant
    ownership RATIO is NOT a fraction — it can validly exceed 1 (immigrants CAN out-own
    non-immigrants in a cell); only the PRODUCT p_imm binds [0,1]. Also used for stocks."""
    f = assert_finite(name, value)
    if f < 0.0:
        raise LoaderError(f"{name}: negative value {f}")
    return f


# Signed-flow carve-out (codex r9-F2): natural increase / net-migration components are
# legitimately signed — validate them with assert_finite ONLY (never nonneg/fraction); the
# natural-increase tripwire's job is to EVALUATE a negative value, not raise on it.


def assert_unique_primary_key(df: pd.DataFrame, keys: list[str], ctx: str) -> None:
    dups = df.duplicated(subset=keys, keep=False)
    if dups.any():
        raise LoaderError(f"{ctx}: duplicate primary key {keys} on {int(dups.sum())} rows")


def assert_year_lattice(years, ctx: str, expected_span: tuple[int, int] | None = None) -> None:
    ys = sorted(set(int(y) for y in years))
    if not ys:
        raise LoaderError(f"{ctx}: empty year index")
    if ys != list(range(ys[0], ys[-1] + 1)):
        raise LoaderError(f"{ctx}: year lattice not contiguous (consecutive diffs must be 1): {ys}")
    if expected_span is not None and (ys[0], ys[-1]) != expected_span:
        raise LoaderError(f"{ctx}: year span {(ys[0], ys[-1])} != expected endpoints {expected_span}")


def assert_uniform_year_domain(df: pd.DataFrame, group_keys: list[str], year_col: str, ctx: str) -> None:
    """Every geography×scenario×sex series must carry the IDENTICAL year set (codex r6-F3);
    a missing terminal year for one series raises (never a silently shortened mean)."""
    domains = df.groupby(group_keys)[year_col].apply(lambda s: frozenset(int(y) for y in s))
    uniq = set(domains)
    if len(uniq) > 1:
        ref = max(uniq, key=len)
        deficient = [k for k, d in domains.items() if d != ref]
        raise LoaderError(f"{ctx}: non-uniform year domain across series (missing terminal year?); "
                          f"deficient groups: {deficient[:5]}")


def assert_statut_sublattice(df: pd.DataFrame, group_keys: list[str], year_col: str,
                             status_col: str, allowed: set[str], ctx: str) -> None:
    """Statut SUB-lattice (codex r10): status values in the metadata's allowed set; exactly ONE
    est→proj transition per series (monotone, no proj→est reversal); and an IDENTICAL PROJECTED-year
    domain across every series — so a proj→est relabel of one geography's terminal year raises even
    though the RAW year lattice is intact (it would silently shorten that geography's ranking mean)."""
    bad = set(df[status_col].astype(str)) - set(allowed)
    if bad:
        raise LoaderError(f"{ctx}: Statut values outside allowed set {sorted(allowed)}: {sorted(bad)}")
    proj_domains = set()
    for key, grp in df.groupby(group_keys):
        g = grp.sort_values(year_col)
        is_proj = [str(s).lower().startswith("proj") for s in g[status_col]]
        if any(is_proj[i] < is_proj[i - 1] for i in range(1, len(is_proj))):
            raise LoaderError(f"{ctx}: series {key} has a proj→est reversal (relabel?) — not a sub-lattice")
        switches = sum(1 for i in range(1, len(is_proj)) if is_proj[i] and not is_proj[i - 1])
        if switches != 1:
            raise LoaderError(f"{ctx}: series {key} has {switches} est→proj transitions (expected exactly 1)")
        proj_domains.add(frozenset(int(y) for y, p in zip(g[year_col], is_proj) if p))
    if len(proj_domains) > 1:
        raise LoaderError(f"{ctx}: non-uniform PROJECTED-year domain across series (a proj→est relabel "
                          f"shortens one geography's ranking mean)")
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_validate.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/loaders/validate.py demoflow/tests/test_validate.py
git commit -m "feat(demoflow): shared loader validation (fraction/nonneg-ratio/signed-flow/PK/year-lattice/Statut-sublattice; §4 r4/r5/r7/r9/r10-F)"
```

---

### Task 9: Geography enum + label normalization + junction maps

**Files:**
- Create: `demoflow/src/demoflow/geography.py`
- Test: `demoflow/tests/test_geography.py`

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_geography.py`:
```python
import pytest

from demoflow.geography import (
    Geography, Scenario, SEX_CODE_TO_GENDER, SCENARIO_LABEL_TO_ENUM,
    normalize_label, classify_geography, IGNORED, require_all_geographies, RA_PROXY_MEMBERS,
)
from demoflow.errors import LoaderError


def test_normalize_strips_whitespace_and_footnote_digits():
    assert normalize_label("RMR de Montréal ") == "RMR de Montréal"
    assert normalize_label("RMR d'Ottawa-Gatineau2") == "RMR d'Ottawa-Gatineau"


def test_modeled_label_maps_to_enum():
    assert classify_geography("RMR de Montréal ") is Geography.MTL_RMR


def test_known_unmodeled_label_is_IGNORED_not_raise():
    # Valid ISQ geography, outside model scope -> IGNORED sentinel (a valid workbook must LOAD).
    assert classify_geography("RMR de Saguenay") is IGNORED
    assert classify_geography("Le Québec") is IGNORED


def test_label_outside_verified_set_raises():
    with pytest.raises(LoaderError, match="verified set|drift"):
        classify_geography("RMR de Nowhere")


def test_require_all_geographies_raises_on_missing_expected():
    with pytest.raises(LoaderError, match="not found"):
        require_all_geographies({Geography.MTL_RMR}, {Geography.MTL_RMR, Geography.QC_RMR}, "ctx")
    require_all_geographies({Geography.MTL_RMR, Geography.QC_RMR},
                            {Geography.MTL_RMR, Geography.QC_RMR}, "ctx")  # complete: no raise


def test_scenario_labels_map_to_enum():
    assert SCENARIO_LABEL_TO_ENUM["Référence (A2026)"] is Scenario.REFERENCE
    assert SCENARIO_LABEL_TO_ENUM["Faible (D2026)"] is Scenario.LOW
    assert SCENARIO_LABEL_TO_ENUM["Fort (E2026)"] is Scenario.HIGH


def test_sex_codes_are_numeric_1_2_3():
    assert SEX_CODE_TO_GENDER[1] == "M"
    assert SEX_CODE_TO_GENDER[2] == "F"
    assert 3 not in SEX_CODE_TO_GENDER  # code 3 is TOTAL, used only for additivity


def test_geography_value_is_a_string():
    assert Geography.MTL_RMR.value == "MTL_RMR"
    assert isinstance(Geography.MTL_RMR.value, str)


def test_ra_proxy_members_flagged():
    assert Geography.LANAUDIERE_RA14_PROXY in RA_PROXY_MEMBERS
    assert Geography.MTL_RMR not in RA_PROXY_MEMBERS
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_geography.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.geography`).

- [ ] **Step 3: Write the implementation**

`demoflow/src/demoflow/geography.py`:
```python
"""Geography + Scenario enums and per-source label junction maps (spec §8).
Junction rule: NORMALIZE first (strip whitespace + trailing footnote digits),
THEN the explicit label->enum map; unknown-after-normalization raises."""
import re
from enum import Enum

from demoflow.errors import LoaderError


class Geography(str, Enum):
    MTL_RMR = "MTL_RMR"
    MTL_ISLAND_RA06 = "MTL_ISLAND_RA06"
    LAVAL_RA13 = "LAVAL_RA13"
    QC_RMR = "QC_RMR"
    HORS_RMR = "HORS_RMR"
    LANAUDIERE_RA14_PROXY = "LANAUDIERE_RA14_PROXY"
    LAURENTIDES_RA15_PROXY = "LAURENTIDES_RA15_PROXY"
    MONTEREGIE_RA16_PROXY = "MONTEREGIE_RA16_PROXY"


class Scenario(str, Enum):
    REFERENCE = "reference"
    LOW = "low"
    HIGH = "high"


# RA rows used as couronne/periphery proxies: ranking members, never balance
# participants, never emitted in ScenarioPrior (spec §7b/§8).
RA_PROXY_MEMBERS = frozenset({
    Geography.LANAUDIERE_RA14_PROXY,
    Geography.LAURENTIDES_RA15_PROXY,
    Geography.MONTEREGIE_RA16_PROXY,
})

# ISQ scenario labels -> enum (spec §8). Missing any of the three for a
# geography x year -> raise (enforced in the loader, Task 10).
SCENARIO_LABEL_TO_ENUM = {
    "Référence (A2026)": Scenario.REFERENCE,
    "Faible (D2026)": Scenario.LOW,
    "Fort (E2026)": Scenario.HIGH,
}

# ISQ numeric sex codes {1,2,3}. 1->M, 2->F. Code 3 is TOTAL, kept out of this
# map and used ONLY for the additivity check (code3 ~= code1+code2) in the loader.
SEX_CODE_TO_GENDER = {1: "M", 2: "F"}

# Normalized ISQ pop/compo geography label -> Geography. RMR labels come from
# pop-as-rmr-base / compo-rmr-base; RA labels from the -ra- workbooks.
_LABEL_TO_GEOGRAPHY = {
    "RMR de Montréal": Geography.MTL_RMR,
    "RMR de Québec": Geography.QC_RMR,
    "Montréal": Geography.MTL_ISLAND_RA06,     # RA06 (île) from pop-as-ra-base
    "Laval": Geography.LAVAL_RA13,             # RA13 == ville (exact)
    "Lanaudière": Geography.LANAUDIERE_RA14_PROXY,
    "Laurentides": Geography.LAURENTIDES_RA15_PROXY,
    "Montérégie": Geography.MONTEREGIE_RA16_PROXY,
    # codex r7-F4: the RMR workbook's OWN literal row supplies HORS_RMR POPULATION directly —
    # HORS_RMR is a modeled geography, NEVER IGNORED and NEVER a residual on the population side.
    "Territoire hors des RMR": Geography.HORS_RMR,
    "Hors RMR": Geography.HORS_RMR,
    "Ailleurs au Québec": Geography.HORS_RMR,
}

_TRAILING_FOOTNOTE = re.compile(r"\d+$")


def normalize_label(raw: str) -> str:
    """Strip surrounding whitespace, then strip a trailing footnote digit run
    (e.g. 'RMR d'Ottawa-Gatineau2' -> "RMR d'Ottawa-Gatineau")."""
    return _TRAILING_FOOTNOTE.sub("", str(raw).strip()).strip()


class _Ignored:
    """Sentinel: a recognized-but-unmodeled geography (spec §8 r4-F2)."""
    __slots__ = ()
    def __repr__(self) -> str:  # noqa: E704
        return "IGNORED"


IGNORED = _Ignored()

# Present-but-UNMODELED labels (the workbooks' verified label set minus the 8 modeled ones):
# RMR workbook's other RMRs + 'Le Québec'; RA workbook's other 12 administrative regions.
# Byte-exact spellings CONFIRMED against the committed workbooks at Task 11 (— vs -, accents).
_IGNORED_LABELS = frozenset({
    "RMR d'Ottawa-Gatineau", "RMR de Saguenay", "RMR de Sherbrooke",
    "RMR de Trois-Rivières", "RMR de Drummondville", "Le Québec", "Ensemble du Québec",
    "Bas-Saint-Laurent", "Saguenay–Lac-Saint-Jean", "Capitale-Nationale", "Mauricie",
    "Estrie", "Outaouais", "Abitibi-Témiscamingue", "Côte-Nord", "Nord-du-Québec",
    "Gaspésie–Îles-de-la-Madeleine", "Chaudière-Appalaches", "Centre-du-Québec",
})


def classify_geography(raw: str) -> "Geography | _Ignored":
    """TOTAL label map over the workbook's verified label set (spec §8 r4-F2):
    modeled label -> Geography; known-unmodeled label -> IGNORED (recognized-and-
    excluded, so a valid workbook LOADS); a label OUTSIDE the verified set -> raise
    (schema drift). Fail-loud is BOTH here (unknown label) AND in
    `require_all_geographies` (a modeled label that went missing)."""
    key = normalize_label(raw)
    geo = _LABEL_TO_GEOGRAPHY.get(key)
    if geo is not None:
        return geo
    if key in _IGNORED_LABELS:
        return IGNORED
    raise LoaderError(f"geography label outside verified set (drift?): {key!r} (from {raw!r})")


def require_all_geographies(found: set[Geography], expected: set[Geography], ctx: str) -> None:
    """Positive completeness check (fail-loud). Raises if any EXPECTED in-scope
    geography is absent after mapping — the guard against a drifted/renamed label
    silently vanishing from the rankings (spec §8 'unknown-after-normalization'
    relocated to 'expected-not-found', which is stronger for model correctness)."""
    missing = expected - found
    if missing:
        raise LoaderError(f"{ctx}: expected geographies not found (schema drift?): "
                          f"{sorted(g.value for g in missing)}")


# In-scope enum members EXPECTED per committed workbook (the positive completeness set).
WORKBOOK_GEOGRAPHIES: dict[str, frozenset[Geography]] = {
    "pop-as-rmr-base.xlsx": frozenset({Geography.MTL_RMR, Geography.QC_RMR, Geography.HORS_RMR}),
    "compo-rmr-base.xlsx": frozenset({Geography.MTL_RMR, Geography.QC_RMR, Geography.HORS_RMR}),
    "pop-as-ra-base.xlsx": frozenset({
        Geography.MTL_ISLAND_RA06, Geography.LAVAL_RA13, Geography.LANAUDIERE_RA14_PROXY,
        Geography.LAURENTIDES_RA15_PROXY, Geography.MONTEREGIE_RA16_PROXY}),
    "compo-ra-base.xlsx": frozenset({
        Geography.MTL_ISLAND_RA06, Geography.LAVAL_RA13, Geography.LANAUDIERE_RA14_PROXY,
        Geography.LAURENTIDES_RA15_PROXY, Geography.MONTEREGIE_RA16_PROXY}),
    "pop-as-qc-base.xlsx": frozenset(),   # QC total: no in-scope enum geography (not used in T1 rankings)
}
```

Both `_LABEL_TO_GEOGRAPHY` (modeled) and `_IGNORED_LABELS` (recognized-unmodeled) spellings are
provisional (from the provisioning-verdict prose) — the byte-exact normalized `Région1` values
MUST be confirmed against the committed workbooks at Task 11. A modeled label that fails to match
surfaces via `require_all_geographies` (expected-not-found); an unmodeled label absent from
`_IGNORED_LABELS` surfaces via `classify_geography` (outside verified set). Both are the intended
fail-loud paths, not a per-row crash on valid out-of-scope geographies.

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_geography.py -v`
Expected: 9 PASS.

Note (do not skip): confirm every workbook label lands in EITHER `_LABEL_TO_GEOGRAPHY` (the 8
modeled) OR `_IGNORED_LABELS` (the rest of the workbook's verified set) at Task 11 — dump the
committed workbook's distinct normalized `Région1` values and reconcile, so a valid workbook LOADS
(no `classify_geography` raise on a real row) while a genuinely new/drifted label still raises.

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/geography.py demoflow/tests/test_geography.py
git commit -m "feat(demoflow): Geography/Scenario enums + normalized label junctions (spec §8)"
```

---

### Task 10: ISQ single-year age-block builder (header-group selection)

**Files:**
- Create: `demoflow/src/demoflow/loaders/isq_ages.py`
- Test: `demoflow/tests/test_isq_ages.py`

Built FIRST so the junction loader (Task 11) imports it (never a forward import). The
single-year `Âge` block must be selected by header GROUP (duplicate `100+` column
names exist across the grouped-age and single-year blocks). pandas does not
forward-fill merged group cells, so we parse the raw sheet with `header=None` and
reconstruct the level-0 groups by forward-fill.

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_isq_ages.py`:
```python
from demoflow.loaders.isq_ages import build_single_year_long
from demoflow.loaders.pins import DATA_DIR


def test_builder_yields_pre_junction_long_rows():
    df = build_single_year_long(DATA_DIR / "pop-as-rmr-base.xlsx")
    assert set(df.columns) == {
        "label", "scenario_label", "year", "status", "sex_code", "age", "population",
    }
    # single-year ages only, 0..100 (100+ capped at 100), no grouped-age labels leaked
    assert df["age"].min() >= 0 and df["age"].max() == 100
    # numeric sex codes {1,2,3} preserved (additivity checked later, Task 11)
    assert set(df["sex_code"].unique()) <= {1, 2, 3}
    # scenario labels are the raw ISQ strings (mapped to enum in Task 11)
    assert "Référence (A2026)" in set(df["scenario_label"])


def test_builder_selects_single_year_block_not_grouped():
    df = build_single_year_long(DATA_DIR / "pop-as-rmr-base.xlsx")
    # single-year block => a contiguous 0..100 age set present for a given key
    ages = sorted(df["age"].unique())
    assert ages == list(range(0, 101))
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_isq_ages.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.loaders.isq_ages`).

- [ ] **Step 3: Write the implementation**

`demoflow/src/demoflow/loaders/isq_ages.py`:
```python
"""Select the single-year 'Âge' header-GROUP block from an ISQ pop workbook and
melt it to pre-junction long rows (spec §8 Age junction). Live-verified: sheet
"Années d'âge", header at 0-indexed rows 6 (groups) + 7 (labels); id columns
Scénario/Code/Région1/Année/Statut/Sexe; the single-year block sits under the
level-0 group label 'Âge' (grouped-age block is under "Groupe d'âge"); a '100+'
label appears in BOTH blocks -> select by GROUP, never by bare name; '100+' -> 100."""
from pathlib import Path

import pandas as pd

from demoflow.errors import LoaderError

SHEET = "Années d'âge"
_ID_LABELS = ("Scénario", "Code", "Région1", "Année", "Statut", "Sexe")
_AGE_GROUP = "Âge"          # single-year block level-0 label (confirm byte-exact vs workbook)
_HDR_GROUP_ROW = 6          # 0-indexed
_HDR_LABEL_ROW = 7
_DATA_FIRST_ROW = 8


def _age_of(label: object) -> int | None:
    s = str(label).strip()
    if s in ("100+", "100 +", "100et+", "100 et +"):
        return 100
    if s.isdigit():
        return int(s)
    return None


def build_single_year_long(path: Path) -> pd.DataFrame:
    rawnh = pd.read_excel(path, sheet_name=SHEET, header=None, engine="openpyxl")
    if rawnh.empty or len(rawnh) <= _DATA_FIRST_ROW:
        raise LoaderError(f"empty/short sheet {SHEET!r} in {path.name}")

    lvl0 = rawnh.iloc[_HDR_GROUP_ROW].ffill()       # reconstruct merged group spans
    lvl1 = rawnh.iloc[_HDR_LABEL_ROW]
    body = rawnh.iloc[_DATA_FIRST_ROW:].reset_index(drop=True)

    id_pos = {}
    for pos, g in lvl0.items():
        gg = str(g).strip() if pd.notna(g) else ""
        if gg in _ID_LABELS and gg not in id_pos:
            id_pos[gg] = pos
    missing = [c for c in _ID_LABELS if c not in id_pos]
    if missing:
        raise LoaderError(f"{path.name}: missing id columns {missing} (schema drift)")

    # single-year age columns: level-0 group == 'Âge' AND level-1 is a year label
    age_pos: dict[int, int] = {}   # age -> column position
    for pos, g in lvl0.items():
        if str(g).strip() != _AGE_GROUP:
            continue
        age = _age_of(lvl1.iloc[pos])
        if age is None:
            continue
        age_pos.setdefault(age, pos)   # first wins; dupes summed below if any
    if sorted(age_pos) != list(range(0, 101)):
        raise LoaderError(
            f"{path.name}: single-year block not a 0..100 span: {sorted(age_pos)[:5]}... "
            f"(header-group selection failed — confirm group label {_AGE_GROUP!r})"
        )

    records = []
    for _, r in body.iterrows():
        base = {
            "label": r.iloc[id_pos["Région1"]],
            "scenario_label": r.iloc[id_pos["Scénario"]],
            "year": int(r.iloc[id_pos["Année"]]),
            "status": r.iloc[id_pos["Statut"]],
            "sex_code": int(r.iloc[id_pos["Sexe"]]),
        }
        for age, pos in age_pos.items():
            val = r.iloc[pos]
            records.append({**base, "age": age, "population": float(val)})
    return pd.DataFrame.from_records(records)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_isq_ages.py -v`
Expected: 2 PASS. If the age span assertion raises, confirm `_AGE_GROUP` and the `100+`
spelling against the workbook (`uv run python -c "import pandas as pd; print(pd.read_excel('data/pop-as-rmr-base.xlsx', sheet_name=\"Années d'âge\", header=None).iloc[6:8].to_string())"`) and adjust the two constants — this is the header-group selection the spec pins.

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/loaders/isq_ages.py demoflow/tests/test_isq_ages.py
git commit -m "feat(demoflow): ISQ single-year age-block builder (header-group selection, spec §8)"
```

---

### Task 11: ISQ population loader — junctions + sex additivity + ORIENTATION guard + PK/year-lattice

**Files:**
- Create: `demoflow/src/demoflow/loaders/isq.py`
- Test: `demoflow/tests/test_isq_loader.py`

Folded spec §8/§4: geography via `classify_geography` (TOTAL map, IGNORED sentinel, unknown →
raise); sex TRIPLE-check (additivity + ORIENTATION guard: 85+ female-mapped > male-mapped in every
geo×year, else swapped map → raise; code-3 excluded); primary-key uniqueness; finite non-negative
populations; year lattice pinned to 2021–2051 with a uniform domain across every geo×scenario×sex
series (codex r2-F5/r4-F2/r4-F3/r5-F1-F2/r6-F3).

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_isq_loader.py`:
```python
import pandas as pd
import pytest

from demoflow.geography import Geography, Scenario
from demoflow.loaders.isq import load_population
from demoflow.errors import LoaderError


def test_load_population_returns_tidy_long_frame():
    df = load_population("pop-as-rmr-base.xlsx")
    assert set(df.columns) >= {"geography", "scenario", "year", "sex", "age", "population", "status"}
    assert set(df["scenario"].unique()) <= {Scenario.REFERENCE, Scenario.LOW, Scenario.HIGH}
    assert set(df["sex"].unique()) <= {"M", "F"}    # code 3 excluded after additivity
    assert {Geography.MTL_RMR, Geography.QC_RMR, Geography.HORS_RMR} <= set(df["geography"].unique())
    assert set(df["geography"].unique()) <= set(Geography)   # IGNORED rows dropped
    # year lattice pinned to 2021-2051 (loader would have raised otherwise)
    assert df["year"].min() == 2021 and df["year"].max() == 2051


def test_all_three_scenarios_present_for_mtl_rmr():
    df = load_population("pop-as-rmr-base.xlsx")
    mtl = df[df["geography"] == Geography.MTL_RMR]
    assert {Scenario.REFERENCE, Scenario.LOW, Scenario.HIGH} <= set(mtl["scenario"].unique())


def test_sex_additivity_violation_raises():
    import demoflow.loaders.isq as isq
    with pytest.raises(LoaderError, match="additivity"):
        isq._check_sex_additivity(code3=100.0, code1=40.0, code2=40.0, ctx="MTL/2035/ref/age75")


def test_sex_orientation_guard_raises_on_swapped_map():   # RED (codex r2-F5)
    import demoflow.loaders.isq as isq
    swapped = pd.DataFrame({
        "geography": [Geography.MTL_RMR, Geography.MTL_RMR],
        "scenario": [Scenario.REFERENCE, Scenario.REFERENCE],
        "year": [2035, 2035], "sex": ["M", "F"], "age": [85, 85],
        "population": [1000.0, 500.0],   # M > F at 85+ => swapped 1<->2 map
    })
    with pytest.raises(LoaderError, match="orientation"):
        isq._check_sex_orientation(swapped, "test")


def test_missing_workbook_raises():
    with pytest.raises(LoaderError, match="not found"):
        load_population("does-not-exist.xlsx")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_isq_loader.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.loaders.isq`).

- [ ] **Step 3: Write the implementation**

`demoflow/src/demoflow/loaders/isq.py`:
```python
"""ISQ population loader (spec §8/§4, codex r2-F5/r4-F2/r4-F3/r5-F1-F2/r6-F3):
geography (TOTAL map with IGNORED sentinel), scenario, sex (additivity + ORIENTATION
guard) junctions; primary-key uniqueness; finite non-negative populations; year lattice
pinned to the expected span with a uniform domain across every geo x scenario x sex series."""
import math
from pathlib import Path

import numpy as np
import pandas as pd

from demoflow.errors import LoaderError
from demoflow.geography import (
    IGNORED, SCENARIO_LABEL_TO_ENUM, SEX_CODE_TO_GENDER,
    WORKBOOK_GEOGRAPHIES, classify_geography, require_all_geographies,
)
from demoflow.loaders.isq_ages import build_single_year_long
from demoflow.loaders.pins import DATA_DIR, verify_pin
from demoflow.loaders.validate import (
    assert_statut_sublattice, assert_unique_primary_key, assert_uniform_year_domain, assert_year_lattice,
)

SEX_ADDITIVITY_RTOL = 1e-6
_EXPECTED_SPAN = {"pop-as-qc-base.xlsx": (2021, 2071)}   # QC total reaches 2071
_DEFAULT_SPAN = (2021, 2051)                              # RMR / RA workbooks
_STATUT_ALLOWED = {"est", "proj"}                        # metadata's allowed Statut set (confirm at probe)


def _check_sex_additivity(code3: float, code1: float, code2: float, ctx: str) -> None:
    if not math.isclose(code3, code1 + code2, rel_tol=SEX_ADDITIVITY_RTOL, abs_tol=1e-6):
        raise LoaderError(f"sex additivity violated at {ctx}: code3={code3} != code1+code2={code1 + code2}")


def _check_sex_orientation(mf: pd.DataFrame, name: str) -> None:
    """85+ female-mapped population must EXCEED male-mapped in every geo x scenario x year
    (universal old-age female survival advantage) — a violation = a swapped 1<->2 map."""
    old = mf[mf["age"] >= 85]
    piv = old.pivot_table(index=["geography", "scenario", "year"], columns="sex",
                          values="population", aggfunc="sum").fillna(0.0)
    f = piv["F"] if "F" in piv.columns else 0.0
    m = piv["M"] if "M" in piv.columns else 0.0
    viol = piv[f <= m]
    if len(viol) > 0:
        raise LoaderError(f"{name}: sex orientation guard failed — 85+ female-mapped <= male-mapped "
                          f"(swapped sex map?) at {list(viol.index)[:3]}")


def _resolve_path(name: str, data_dir: Path | None) -> Path:
    path = (data_dir or DATA_DIR) / name
    if not path.exists():
        raise LoaderError(f"workbook not found: {path} (re-download is a fallback, spec §4)")
    verify_pin(path, name)
    return path


def load_population(name: str, data_dir: Path | None = None) -> pd.DataFrame:
    path = _resolve_path(name, data_dir)
    long = build_single_year_long(path)

    # Geography: TOTAL map -> Geography | IGNORED (unknown label raises); drop IGNORED rows.
    long["geo_cls"] = long["label"].map(classify_geography)
    long = long[long["geo_cls"].map(lambda g: g is not IGNORED)].copy()
    long["geography"] = long["geo_cls"]
    require_all_geographies(set(long["geography"]),
                            set(WORKBOOK_GEOGRAPHIES.get(name, frozenset())), name)

    unknown_sc = set(long["scenario_label"]) - set(SCENARIO_LABEL_TO_ENUM)
    if unknown_sc:
        raise LoaderError(f"unknown ISQ scenario labels: {sorted(unknown_sc)}")
    long["scenario"] = long["scenario_label"].map(SCENARIO_LABEL_TO_ENUM)

    # Sex additivity (code3 ~= code1 + code2) per geo x scenario x year x age.
    keyed = long.pivot_table(index=["geography", "scenario", "year", "age", "status"],
                             columns="sex_code", values="population", aggfunc="sum")
    for idx, row in keyed.iterrows():
        c3 = row.get(3, float("nan"))
        if pd.notna(c3):
            _check_sex_additivity(float(c3), float(row.get(1, float("nan"))),
                                  float(row.get(2, float("nan"))), str(idx))

    mf = long[long["sex_code"].isin(SEX_CODE_TO_GENDER)].copy()
    mf["sex"] = mf["sex_code"].map(SEX_CODE_TO_GENDER)

    # Finite + non-negative populations (r4-F3: reject NaN AND ±Inf).
    if (mf["population"] < 0).any() or not np.isfinite(mf["population"].to_numpy()).all():
        raise LoaderError(f"{name}: negative or non-finite population cell")

    _check_sex_orientation(mf, name)   # r2-F5 orientation guard

    out = mf[["geography", "scenario", "year", "sex", "age", "population", "status"]].reset_index(drop=True)

    # Primary key + pinned/uniform year lattice (r5-F2, r6-F3) + Statut sub-lattice (r10).
    assert_unique_primary_key(out, ["geography", "scenario", "year", "sex", "age"], name)
    assert_year_lattice(out["year"].unique(), name, expected_span=_EXPECTED_SPAN.get(name, _DEFAULT_SPAN))
    assert_uniform_year_domain(out, ["geography", "scenario", "sex"], "year", name)
    assert_statut_sublattice(out, ["geography", "scenario", "sex"], "year", "status", _STATUT_ALLOWED, name)
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_isq_loader.py -v`
Expected: 5 PASS. (If `classify_geography` raises on a real row, the workbook carries a label
in NEITHER `_LABEL_TO_GEOGRAPHY` nor `_IGNORED_LABELS` — dump the distinct normalized `Région1`
values and reconcile Task 9's maps. If `require_all_geographies` raises, a modeled label's
byte-exact spelling is wrong. If `assert_year_lattice` raises on span, confirm the workbook's
actual year endpoints and adjust `_EXPECTED_SPAN`/`_DEFAULT_SPAN`.)

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/loaders/isq.py demoflow/tests/test_isq_loader.py
git commit -m "feat(demoflow): ISQ loader — classify+IGNORED, sex orientation guard, PK + pinned/uniform year lattice (§8/§4)"
```

### Task 12: ISQ compo loader — immigrant-permanent arrival flows

**Files:**
- Create: `demoflow/src/demoflow/loaders/compo.py`
- Test: `demoflow/tests/test_compo_loader.py`

Live-verified: single sheet `"Scénarios de 2026"`, deep header rows 5–9, `"Immigrants
permanents"` at 0-indexed column **16** (group `"Migration internationale"`),
`"Solde des résidents non permanents"` at column **18**; data from Excel row 11. This
is the §6 immigrant-arrival-flow source (I2: it DECOMPOSES the ISQ population, never adds).

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_compo_loader.py`:
```python
import pytest

from demoflow.geography import Geography, Scenario
from demoflow.loaders.compo import load_immigrant_flows
from demoflow.errors import LoaderError


def test_load_immigrant_flows_tidy():
    df = load_immigrant_flows("compo-rmr-base.xlsx")
    assert set(df.columns) == {"geography", "scenario", "year", "immigrants_permanents", "npr_net_flow"}
    assert Geography.MTL_RMR in set(df["geography"].unique())
    assert {Scenario.REFERENCE, Scenario.LOW, Scenario.HIGH} <= set(df["scenario"].unique())
    assert (df["immigrants_permanents"] >= 0).all()


def test_header_token_drift_raises(tmp_path):
    import demoflow.loaders.compo as compo
    with pytest.raises(LoaderError, match="header token"):
        compo._verify_header_tokens({16: "Naissances", 18: "Décès"})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_compo_loader.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.loaders.compo`).

- [ ] **Step 3: Write the implementation**

`demoflow/src/demoflow/loaders/compo.py`:
```python
"""ISQ compo loader (spec §6). Live-verified: sheet "Scénarios de 2026"; the
immigrant-permanent arrival flow is column 16 ("Immigrants" / "permanents"), the
net non-permanent-resident flow is column 18 ("Solde" / "non permanents"). We pin
those positions and FAIL LOUD if the header tokens at them drift (schema guard).
id columns: Scénario(0), Code(1), Région1(2), Année(3)."""
from pathlib import Path

import pandas as pd

from demoflow.errors import LoaderError
from demoflow.geography import (
    IGNORED, SCENARIO_LABEL_TO_ENUM, WORKBOOK_GEOGRAPHIES, classify_geography, require_all_geographies,
)
from demoflow.loaders.pins import DATA_DIR, verify_pin

SHEET = "Scénarios de 2026"
COL_SCENARIO, COL_REGION, COL_YEAR = 0, 2, 3
COL_IMMIG_PERM, COL_NPR_NET = 16, 18
_DATA_FIRST_ROW = 10  # 0-indexed (Excel row 11)


def _verify_header_tokens(tokens_at: dict[int, str]) -> None:
    """Raise if the header tokens at the pinned positions are not the migration
    columns (guards against a re-ordered/re-editioned workbook)."""
    imm = str(tokens_at.get(COL_IMMIG_PERM, "")).lower()
    npr = str(tokens_at.get(COL_NPR_NET, "")).lower()
    if "immigrant" not in imm and "permanent" not in imm:
        raise LoaderError(f"header token drift at col {COL_IMMIG_PERM}: {tokens_at.get(COL_IMMIG_PERM)!r}")
    if "solde" not in npr and "permanent" not in npr:
        raise LoaderError(f"header token drift at col {COL_NPR_NET}: {tokens_at.get(COL_NPR_NET)!r}")


def load_immigrant_flows(name: str = "compo-rmr-base.xlsx", data_dir: Path | None = None) -> pd.DataFrame:
    path = (data_dir or DATA_DIR) / name
    if not path.exists():
        raise LoaderError(f"workbook not found: {path}")
    verify_pin(path, name)
    rawnh = pd.read_excel(path, sheet_name=SHEET, header=None, engine="openpyxl")
    if rawnh.empty or len(rawnh) <= _DATA_FIRST_ROW:
        raise LoaderError(f"empty/short sheet {SHEET!r} in {name}")

    # header token check across the multi-row header block (rows 5..9), forward-filled.
    hdr = rawnh.iloc[5:10].ffill(axis=0).apply(lambda col: " ".join(str(v) for v in col if pd.notna(v)))
    _verify_header_tokens({COL_IMMIG_PERM: hdr.iloc[COL_IMMIG_PERM], COL_NPR_NET: hdr.iloc[COL_NPR_NET]})

    body = rawnh.iloc[_DATA_FIRST_ROW:].reset_index(drop=True)
    records = []
    for _, r in body.iterrows():
        geo = classify_geography(r.iloc[COL_REGION])   # Geography | IGNORED; unknown label raises
        if geo is IGNORED:
            continue  # recognized-unmodeled geography ('Le Québec', other RMRs) — skipped
        sc_key = str(r.iloc[COL_SCENARIO]).strip()
        if sc_key not in SCENARIO_LABEL_TO_ENUM:
            # an IN-SCOPE geography with an unrecognized scenario label is genuine drift.
            raise LoaderError(f"{name}: in-scope geography {geo.value} carries unknown scenario {sc_key!r}")
        records.append({
            "geography": geo,
            "scenario": SCENARIO_LABEL_TO_ENUM[sc_key],
            "year": int(r.iloc[COL_YEAR]),
            "immigrants_permanents": float(r.iloc[COL_IMMIG_PERM]),
            "npr_net_flow": float(r.iloc[COL_NPR_NET]),
        })
    df = pd.DataFrame.from_records(records)
    if df.empty:
        raise LoaderError(f"{name}: no rows mapped to the Geography enum (schema drift)")
    require_all_geographies(set(df["geography"]),
                            set(WORKBOOK_GEOGRAPHIES.get(name, frozenset())), name)
    if (df["immigrants_permanents"] < 0).any():
        raise LoaderError(f"{name}: negative immigrant-permanent flow")
    return df


def write_closed_cohort_evidence(df, out_path) -> None:
    """Record the migration magnitude the closed-cohort assumption omits (spec §5 r3-F2):
    post-entry 75+ net migration is NOT modeled; the compo total bounds it (senior migration
    is a thin fraction). This note is the assumption's evidence."""
    from pathlib import Path
    tot_imm = float(df["immigrants_permanents"].sum())
    tot_npr = float(df["npr_net_flow"].sum())
    Path(out_path).write_text(
        "# Closed-cohort migration assumption — evidence (spec §5 r3-F2)\n\n"
        "The 75+ roll-forward is CLOSED after band entry: post-entry net migration at ages 75+ "
        "is OMITTED (a stated assumption, sensitivity remark in outputs — NOT a modeled mechanism).\n\n"
        f"- compo total immigrants_permanents (all geos/scenarios/years): {tot_imm:,.0f}\n"
        f"- compo total npr_net_flow: {tot_npr:,.0f}\n"
        "- compo is NOT age-structured, so the 75+ share is not directly available; senior migration "
        "is a thin fraction of these totals -> the omitted term is small vs the modeled 75+ flows.\n"
    )
```

Note (shared policy with Task 11): both ISQ loaders use `classify_geography` — modeled → enum,
recognized-unmodeled → IGNORED (skipped), a label OUTSIDE the verified set → raise; fail-loud is
that raise PLUS the `require_all_geographies` completeness check PLUS the strict scenario check.
Every other degenerate (negative flow, header-token drift, missing file, empty result) still raises.

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_compo_loader.py -v`
Expected: 2 PASS.

- [ ] **Step 4b: Record the closed-cohort migration evidence (spec §5 r3-F2) + commit it**

Run:
```bash
cd demoflow && uv run python -c "from demoflow.loaders.compo import load_immigrant_flows, write_closed_cohort_evidence; write_closed_cohort_evidence(load_immigrant_flows('compo-rmr-base.xlsx'), 'probes/closed-cohort-migration.md')"
```
Expected: writes `probes/closed-cohort-migration.md` recording the compo migration totals as the
closed-cohort assumption's evidence.

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/loaders/compo.py demoflow/tests/test_compo_loader.py demoflow/probes/closed-cohort-migration.md
git commit -m "feat(demoflow): ISQ compo loader (classify+IGNORED) + closed-cohort migration evidence (§6, §5 r3-F2)"
```

---

### Task 13: Census ownership + headship loaders (HORS_RMR = province net of ALL CMAs)

**Files:**
- Create: `demoflow/src/demoflow/loaders/census.py`
- Create: `demoflow/data/ownership_by_geo_age.json` (committed ownership fixture)
- Create: `demoflow/data/headship_by_age.json` (committed base-year headship fixture)
- Test: `demoflow/tests/test_census_ownership.py`

Ownership is a HARD input (no silent fallback), provenance-verified (56.2% owner, 75+, MTL CMA).
**HORS_RMR = Québec-province tenure NET of ALL QC CMAs** — not just MTL+QC (the other RMRs are
neither MTL/QC nor hors-RMR; codex r4-F2); CA caveat recorded (r5-F7). Ownership + headship rates
are fractions asserted ∈[0,1] (r5-F1). Headship (households/person by age) is the base-year Census
curve the OwnerStock equation and native formation consume, held PIT-fixed (spec §7 r3-F3).

- [ ] **Step 1a: Create the committed ownership fixture**

`demoflow/data/ownership_by_geo_age.json`:
```json
{
  "_provenance": {
    "source": "StatCan Census 2021, Table 98-10-0231-01 (tenure x age of primary maintainer)",
    "as_of": "2021",
    "hors_rmr_method": "province_net_of_ALL_QC_CMAs",
    "hors_rmr_ca_caveat": "P2 pulls province + EVERY QC CMA (codex r4-F2); a published non-CMA/CA row EXCLUDES Census Agglomerations while province-minus-CMAs INCLUDES them (r5-F7) — use the published row only if it reconciles exactly against the computed residual, else compute the residual and record what HORS_RMR denotes",
    "notes": "MTL/QC CMA rates verified (MTL 75+ = 0.562). Populate from data/census_tenure_age_98100231.csv when the P2 pull committed it; else verified anchors + borrowed_prior."
  },
  "rates": {
    "MTL_RMR":  {"25-54": 0.48, "55-64": 0.66, "65-74": 0.63, "75+": 0.562},
    "QC_RMR":   {"25-54": 0.52, "55-64": 0.68, "65-74": 0.66, "75+": 0.60},
    "HORS_RMR": {"25-54": 0.60, "55-64": 0.75, "65-74": 0.73, "75+": 0.68, "_flag": "borrowed_prior"},
    "MTL_ISLAND_RA06": {"25-54": 0.34, "55-64": 0.50, "65-74": 0.48, "75+": 0.44, "_flag": "borrowed_prior"},
    "LAVAL_RA13": {"25-54": 0.55, "55-64": 0.72, "65-74": 0.70, "75+": 0.65, "_flag": "borrowed_prior"},
    "LANAUDIERE_RA14_PROXY": {"25-54": 0.62, "55-64": 0.78, "65-74": 0.76, "75+": 0.71, "_flag": "borrowed_prior"},
    "LAURENTIDES_RA15_PROXY": {"25-54": 0.61, "55-64": 0.77, "65-74": 0.75, "75+": 0.70, "_flag": "borrowed_prior"},
    "MONTEREGIE_RA16_PROXY": {"25-54": 0.60, "55-64": 0.76, "65-74": 0.74, "75+": 0.69, "_flag": "borrowed_prior"}
  }
}
```
Non-anchor rates are `borrowed_prior` until the P2 pull refines them; only MTL 75+ = 0.562 is
verified. The golden artifact (Task 30) pins whatever vintage is committed here.

- [ ] **Step 1b: Create the committed base-year headship fixture**

`demoflow/data/headship_by_age.json` (households maintained per person by age band; base-year
Census, PIT-fixed — spec §7 r3-F3):
```json
{
  "_provenance": {"source": "Census 2021 QC headship (maintainers/persons) by age; base-year PIT-fixed",
                  "as_of": "2021", "flag": "borrowed_prior"},
  "headship": {"0-19": 0.02, "20-34": 0.40, "35-54": 0.48, "55-64": 0.52, "65-74": 0.56, "75+": 0.62}
}
```

- [ ] **Step 2: Write the failing test**

`demoflow/tests/test_census_ownership.py`:
```python
import json

import pytest

from demoflow.geography import Geography
from demoflow.loaders.census import (
    load_ownership_rates, ownership_rate, load_headship_rates, headship_rate,
)
from demoflow.errors import LoaderError


def test_mtl_rmr_75plus_matches_verified_anchor():
    rates = load_ownership_rates()
    assert ownership_rate(rates, Geography.MTL_RMR, age=78) == pytest.approx(0.562, abs=1e-6)


def test_every_enum_geography_has_a_rate():
    rates = load_ownership_rates()
    for geo in Geography:
        assert 0.0 <= ownership_rate(rates, geo, age=80) <= 1.0   # strict join + fraction


def test_unknown_age_band_raises():
    rates = load_ownership_rates()
    with pytest.raises(LoaderError, match="age band"):
        ownership_rate(rates, Geography.MTL_RMR, age=20)   # below the modeled 25+ bands


def test_out_of_unit_ownership_rate_raises(tmp_path):
    (tmp_path / "ownership_by_geo_age.json").write_text(json.dumps(
        {"rates": {g.value: {"75+": 1.5} for g in Geography}}))
    rates = load_ownership_rates(data_dir=tmp_path)
    with pytest.raises(LoaderError, match=r"\[0, ?1\]|fraction"):
        ownership_rate(rates, Geography.MTL_RMR, age=80)


def test_headship_curve_covers_all_ages_and_is_fraction():
    hs = load_headship_rates()
    for age in (10, 30, 45, 60, 70, 90):
        assert 0.0 <= headship_rate(hs, age) <= 1.0
```

- [ ] **Step 3: Write the implementation**

`demoflow/src/demoflow/loaders/census.py`:
```python
"""Census ownership + headship loaders (spec §8/§7). Ownership: owner-maintainer
rate by geography x age band, STRICT full-geography join, fractions asserted in
[0,1]; HORS_RMR is province-net-of-ALL-QC-CMAs (codex r4-F2), recorded in
_provenance. Headship: base-year households/person by age band (PIT-fixed, §7 r3-F3)."""
import json
from pathlib import Path

from demoflow.errors import LoaderError
from demoflow.geography import Geography
from demoflow.loaders.pins import DATA_DIR
from demoflow.loaders.validate import assert_fraction

_AGE_BANDS = (("25-54", 25, 54), ("55-64", 55, 64), ("65-74", 65, 74), ("75+", 75, 200))
_HEADSHIP_BANDS = (("0-19", 0, 19), ("20-34", 20, 34), ("35-54", 35, 54),
                   ("55-64", 55, 64), ("65-74", 65, 74), ("75+", 75, 200))


def load_ownership_rates(data_dir: Path | None = None) -> dict:
    path = (data_dir or DATA_DIR) / "ownership_by_geo_age.json"
    if not path.exists():
        raise LoaderError(f"ownership fixture not found: {path}")
    rates = json.loads(path.read_text()).get("rates", {})
    missing = [g.value for g in Geography if g.value not in rates]
    if missing:
        raise LoaderError(f"ownership rate missing for geographies: {missing} (strict join)")
    return rates


def _band_for(age: int, bands) -> str:
    for label, lo, hi in bands:
        if lo <= age <= hi:
            return label
    raise LoaderError(f"no modeled age band for age {age}")


def ownership_rate(rates: dict, geography: Geography, age: int) -> float:
    band = _band_for(age, _AGE_BANDS)   # 55+ only -> raises "age band" for younger ages
    geo_rates = rates.get(geography.value)
    if geo_rates is None or band not in geo_rates:
        raise LoaderError(f"no ownership rate for {geography.value} band {band}")
    return assert_fraction(f"ownership[{geography.value},{band}]", geo_rates[band])


def load_headship_rates(data_dir: Path | None = None) -> dict:
    path = (data_dir or DATA_DIR) / "headship_by_age.json"
    if not path.exists():
        raise LoaderError(f"headship fixture not found: {path}")
    return json.loads(path.read_text()).get("headship", {})


def headship_rate(headship: dict, age: int) -> float:
    band = _band_for(age, _HEADSHIP_BANDS)
    if band not in headship:
        raise LoaderError(f"no headship rate for band {band}")
    return assert_fraction(f"headship[{band}]", headship[band])
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_census_ownership.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/loaders/census.py demoflow/data/ownership_by_geo_age.json demoflow/data/headship_by_age.json demoflow/tests/test_census_ownership.py
git commit -m "feat(demoflow): Census ownership + headship loaders (HORS_RMR=province-net-of-all-CMAs, fractions; §8/§7)"
```

---

### Task 14: IRCC PR-landings loader (tripwire input; UNKNOWN when absent)

**Files:**
- Create: `demoflow/src/demoflow/loaders/ircc.py`
- Test: `demoflow/tests/test_ircc_loader.py`

IRCC PR-by-CMA feeds the tripwire (realized landings vs MIFI plan), NOT the demand
model. Per spec §7c it may be UNAVAILABLE → the tripwire reports UNKNOWN (never a stale
within-band). So this loader returns an availability signal, not a hard raise on absence;
a PRESENT-but-malformed file still raises (drift).

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_ircc_loader.py`:
```python
import pytest

from demoflow.loaders.ircc import load_pr_landings, PRLandings
from demoflow.errors import LoaderError


def test_absent_file_is_unavailable_not_raise(tmp_path):
    result = load_pr_landings(data_dir=tmp_path)
    assert isinstance(result, PRLandings)
    assert result.available is False
    assert result.reason and "not found" in result.reason.lower()


def test_present_but_empty_raises(tmp_path):
    (tmp_path / "ircc_pr_by_cma.csv").write_text("")
    with pytest.raises(LoaderError, match="empty"):
        load_pr_landings(data_dir=tmp_path)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_ircc_loader.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.loaders.ircc`).

- [ ] **Step 3: Write the implementation**

`demoflow/src/demoflow/loaders/ircc.py`:
```python
"""IRCC PR-landings loader (spec §7c tripwire input). Absent file -> UNAVAILABLE
(tripwire reports UNKNOWN). Present-but-malformed -> LoaderError."""
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from demoflow.errors import LoaderError
from demoflow.loaders.pins import DATA_DIR


@dataclass(frozen=True)
class PRLandings:
    available: bool
    reason: str = ""
    frame: pd.DataFrame | None = None


def load_pr_landings(data_dir: Path | None = None) -> PRLandings:
    path = (data_dir or DATA_DIR) / "ircc_pr_by_cma.csv"
    if not path.exists():
        return PRLandings(available=False, reason=f"IRCC PR CSV not found: {path}")
    if path.stat().st_size == 0:
        raise LoaderError(f"IRCC PR CSV is empty: {path}")
    df = pd.read_csv(path, dtype=str)
    if df.empty:
        raise LoaderError(f"IRCC PR CSV has no data rows: {path}")
    return PRLandings(available=True, frame=df)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_ircc_loader.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/loaders/ircc.py demoflow/tests/test_ircc_loader.py
git commit -m "feat(demoflow): IRCC PR-landings loader (UNAVAILABLE when absent; spec §7c)"
```

---

### Task 15: Constants module (MIFI / CMHC / Myers + documented anchors)

**Files:**
- Create: `demoflow/src/demoflow/loaders/constants.py`
- Test: `demoflow/tests/test_constants.py`

Versioned scalar anchors with `as_of` + source citations (spec §4). **`couple_share` is
NOT a constant here** (folded spec §5/§11.3 — per-sex, no invented default; it lives in the
living-arrangement loader, Task 15b, cited-or-raise). `collective_share` stays a documented
anchor (spec sanctions it) but MUST be probe-refinable and asserted ∈[0,1]. The
immigrant ownership RATIO + immigrant headship live in the join table (Task 24b).

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_constants.py`:
```python
from demoflow.loaders.constants import CONSTANTS, Anchor


def test_cmhc_senior_sale_anchor():
    a = CONSTANTS["cmhc_senior_sale_5yr"]
    assert isinstance(a, Anchor)
    assert a.value == 0.36 and a.as_of and a.source


def test_myers_retention_envelope_and_reconciliation_band():
    assert CONSTANTS["myers_retention_envelope"].value == (0.26, 0.31)
    assert CONSTANTS["reconciliation_band"].value == (0.20, 0.40)


def test_couple_share_is_NOT_a_constant():
    # folded-spec blocker fix: no invented couple_share default (§5 per-sex, §11.3 cited-or-raise).
    assert "couple_share" not in CONSTANTS


def test_collective_share_is_fraction_and_refinable():
    a = CONSTANTS["collective_share_75plus"]
    assert 0.0 <= a.value <= 1.0 and a.flag == "borrowed_prior"   # probe-refinable, [0,1]-valid


def test_living_alone_vitrine_fallback_band():
    a = CONSTANTS["living_alone_vitrine"]
    assert a.value == 0.28 and a.band == (0.24, 0.34) and a.flag == "borrowed_prior"


def test_mifi_pr_plan_level():
    assert CONSTANTS["mifi_pr_annual_plan"].value == 45000
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_constants.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.loaders.constants`).

- [ ] **Step 3: Write the implementation**

`demoflow/src/demoflow/loaders/constants.py`:
```python
"""Versioned scalar anchors (spec §4). Each carries as_of + source; tripwires
compare realized values against them (Task 28). NO couple_share here (folded §5:
per-sex, cited-or-raise in the living-arrangement loader). collective_share is a
documented anchor, probe-refinable and [0,1]-valid."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Anchor:
    value: object
    as_of: str
    source: str
    band: tuple | None = None
    flag: str | None = None


CONSTANTS = {
    "cmhc_senior_sale_5yr": Anchor(
        0.36, "2021", "CMHC senior-sale rate, 75+, QC (survivor-conditional, 5yr)"),
    "myers_retention_envelope": Anchor(
        (0.26, 0.31), "literature", "Myers all-cause decade retention envelope (75+ owners)"),
    "reconciliation_band": Anchor(
        (0.20, 0.40), "spec §5", "Myers envelope widened -> decade retention gate"),
    "living_alone_vitrine": Anchor(
        0.28, "2021", "ISQ vitrine vieillissement (65+, QC-wide) — POOLED fallback the living-"
        "arrangement loader applies per-sex when the Census cross-tab is absent",
        band=(0.24, 0.34), flag="borrowed_prior"),
    "collective_share_75plus": Anchor(
        0.04, "2021", "Census collective-dwelling share, 75+ (excluded before household conversion)",
        band=(0.02, 0.08), flag="borrowed_prior"),
    "mifi_pr_annual_plan": Anchor(
        45000, "2026", "MIFI immigration plan level (PR/yr)"),
    "q_live_five_year": Anchor(
        0.36, "2021", "CMHC survivor-conditional 5yr sale rate -> annualized to q_live", band=(0.06, 0.11)),
}


# RUN CONTRACT (codex r8-F1): the headline run evaluates every banded assumption at its declared
# CENTRAL value; band ENDPOINTS enter ONLY the robustness sweep (per-geography rank_stable). The
# central values + sweep grid are enumerated HERE and covered by assumptions_hash — the hash
# identifies the selection; the spec's central-value rule DETERMINES it.
CENTRAL_ASSUMPTIONS = {
    "q_live_per_year": 0.085,          # flat age-shape (annualized 1-(1-0.36)^(1/5))
    "phi_voluntary": 0.9,
    "estate_eventual_fraction": 0.725,
    "estate_lag_years": 2,
    "immigrant_ratio_center": 0.62,    # per-geography ownership ratio band center
}
SWEEP_GRID = {                          # endpoints for the robustness sweep, never the headline
    "q_live_per_year": (0.06, 0.11),
    "estate_eventual_fraction": (0.6, 0.85),
    "estate_lag_years": (1, 3),
}


def assumptions_hash() -> str:
    import hashlib
    import json
    payload = json.dumps({"central": CENTRAL_ASSUMPTIONS, "sweep": SWEEP_GRID}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
```

- [ ] **Step 4: Run to verify it passes**

Add to `demoflow/tests/test_constants.py`:
```python
def test_central_assumptions_and_hash():
    from demoflow.loaders.constants import CENTRAL_ASSUMPTIONS, SWEEP_GRID, assumptions_hash
    assert CENTRAL_ASSUMPTIONS["q_live_per_year"] == 0.085
    assert CENTRAL_ASSUMPTIONS["estate_eventual_fraction"] == 0.725
    assert CENTRAL_ASSUMPTIONS["estate_lag_years"] == 2
    # every central value lies within (or at) its sweep endpoints
    for k, (lo, hi) in SWEEP_GRID.items():
        assert lo <= CENTRAL_ASSUMPTIONS[k] <= hi
    assert isinstance(assumptions_hash(), str) and len(assumptions_hash()) == 16
    assert assumptions_hash() == assumptions_hash()   # deterministic
```

Run: `cd demoflow && uv run pytest tests/test_constants.py -v`
Expected: 7 PASS. (The executor updates `collective_share_75plus` from a firmer Census figure
when P3 lands it, keeping the `borrowed_prior` flag otherwise.)

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/loaders/constants.py demoflow/tests/test_constants.py
git commit -m "feat(demoflow): scalar anchor constants (couple_share REMOVED — per-sex cited-or-raise; §5/§11.3)"
```

---

### Task 15b: Living-arrangement loader (per-sex living_alone + couple_share, cited-or-raise)

**Files:**
- Create: `demoflow/src/demoflow/loaders/living_arrangement.py`
- Create: `demoflow/data/living_arrangement.json` (committed per-sex rates)
- Test: `demoflow/tests/test_living_arrangement.py`

Folded spec §5 + §11.3: initialization uses **per-sex** `living_alone_rate_s` and
`couple_share_s`. `living_alone` falls back to the vitrine (28%, widened) per-sex; **`couple_share`
has NO invented default** — it comes from the Census cross-tab (P3) or a cited province-level
value, and if NEITHER is present the loader RAISES (LoaderError). All fractions asserted ∈[0,1].

- [ ] **Step 1: Create the committed per-sex rates fixture**

`demoflow/data/living_arrangement.json` (per-sex living_alone + couple_share by age band; a
`_default` block applies where a geography has no override — the executor adds Census-derived
per-geography overrides from P3 so the couple-balance gate passes on real populations):
```json
{
  "_provenance": {
    "living_alone_source": "P3 Census cross-tab (household type x age x SEX) when available; else vitrine 28% widened per-sex, borrowed_prior",
    "couple_share_source": "Census 2021 QC province-level per-sex coupled share (citation) — NO invented default; refine per-geo via P3",
    "as_of": "2021",
    "calibration_note": "couple_share_s values are set so coupled_m ~= coupled_f (|diff|/max <= 0.25) on the real ISQ populations; executor calibrates per-geo from P3 or the pipeline raises CalibrationError (the gate doing its job)"
  },
  "_default": {
    "75+": {"M": {"living_alone": 0.28, "couple_share": 0.55}, "F": {"living_alone": 0.34, "couple_share": 0.50}},
    "85+": {"M": {"living_alone": 0.34, "couple_share": 0.52}, "F": {"living_alone": 0.50, "couple_share": 0.30}}
  },
  "overrides": {}
}
```

- [ ] **Step 2: Write the failing test**

`demoflow/tests/test_living_arrangement.py`:
```python
import json

import pytest

from demoflow.geography import Geography
from demoflow.loaders.living_arrangement import (
    load_living_arrangement, living_alone_rate, couple_share,
)
from demoflow.errors import LoaderError


def test_per_sex_rates_present_and_fractions():
    la = load_living_arrangement()
    for sex in ("M", "F"):
        lar = living_alone_rate(la, Geography.MTL_RMR, age=80, sex=sex)
        cs = couple_share(la, Geography.MTL_RMR, age=80, sex=sex)
        assert 0.0 <= lar <= 1.0 and 0.0 <= cs <= 1.0


def test_missing_couple_share_raises_no_invented_default(tmp_path):
    # a fixture with living_alone but NO couple_share must RAISE (spec §11.3).
    bad = tmp_path / "living_arrangement.json"
    bad.write_text(json.dumps({"_default": {"75+": {"M": {"living_alone": 0.28}, "F": {"living_alone": 0.34}}}}))
    la = load_living_arrangement(data_dir=tmp_path)
    with pytest.raises(LoaderError, match="couple_share"):
        couple_share(la, Geography.MTL_RMR, age=80, sex="M")


def test_out_of_unit_fraction_raises(tmp_path):
    bad = tmp_path / "living_arrangement.json"
    bad.write_text(json.dumps({"_default": {"75+": {
        "M": {"living_alone": 1.4, "couple_share": 0.5}, "F": {"living_alone": 0.3, "couple_share": 0.5}}}}))
    la = load_living_arrangement(data_dir=tmp_path)
    with pytest.raises(LoaderError, match=r"\[0, ?1\]|fraction"):
        living_alone_rate(la, Geography.MTL_RMR, age=80, sex="M")
```

- [ ] **Step 3: Write the implementation**

`demoflow/src/demoflow/loaders/living_arrangement.py`:
```python
"""Per-sex living-arrangement rates (spec §5, §11.3). living_alone falls back to
the vitrine per-sex; couple_share is cited-or-raise (NO invented default). All
fractions asserted in [0,1] (validate.assert_fraction)."""
import json
from pathlib import Path

from demoflow.errors import LoaderError
from demoflow.geography import Geography
from demoflow.loaders.constants import CONSTANTS
from demoflow.loaders.pins import DATA_DIR
from demoflow.loaders.validate import assert_fraction

_BANDS = (("75+", 75, 84), ("85+", 85, 200))


def load_living_arrangement(data_dir: Path | None = None) -> dict:
    path = (data_dir or DATA_DIR) / "living_arrangement.json"
    if not path.exists():
        raise LoaderError(f"living-arrangement fixture not found: {path}")
    return json.loads(path.read_text())


def _band(age: int) -> str:
    for label, lo, hi in _BANDS:
        if lo <= age <= hi:
            return label
    raise LoaderError(f"no living-arrangement band for age {age} (75+ only)")


def _cell(la: dict, geography: Geography, age: int, sex: str) -> dict:
    band = _band(age)
    over = la.get("overrides", {}).get(geography.value, {})
    block = over.get(band) or la.get("_default", {}).get(band)
    if block is None or sex not in block:
        raise LoaderError(f"no living-arrangement cell for {geography.value} {band} {sex}")
    return block[sex]


def living_alone_rate(la: dict, geography: Geography, age: int, sex: str) -> float:
    cell = _cell(la, geography, age, sex)
    if "living_alone" in cell:
        return assert_fraction("living_alone", cell["living_alone"])
    # per-sex vitrine fallback (borrowed_prior) — living_alone has a documented default.
    return assert_fraction("living_alone", CONSTANTS["living_alone_vitrine"].value)


def couple_share(la: dict, geography: Geography, age: int, sex: str) -> float:
    cell = _cell(la, geography, age, sex)
    if "couple_share" not in cell:
        # NO invented default (spec §11.3): cited-or-raise.
        raise LoaderError(
            f"couple_share missing for {geography.value} {sex} — Census cross-tab or cited "
            f"province value required (no invented default, spec §11.3)")
    return assert_fraction("couple_share", cell["couple_share"])
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_living_arrangement.py -v`
Expected: 3 PASS. (Depends on Task 8b `validate.assert_fraction`; if run before it, add Task 8b first.)

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/loaders/living_arrangement.py demoflow/data/living_arrangement.json demoflow/tests/test_living_arrangement.py
git commit -m "feat(demoflow): per-sex living-arrangement loader (couple_share cited-or-raise; §5/§11.3)"
```

---

### Task 16: Import-direction contract tests (demoflow ⊥ hde, both ways)

**Files:**
- Test: `demoflow/tests/test_import_direction.py`

`demoflow` must never import `hde` or hde's `mcp_server`. It MAY import
`mcp_server.engine.mortality` — that resolves to **actuarial-system's** `mcp_server`
(the only one in demoflow's env), so the contract forbids `hde` specifically (grep +
`hde not in sys.modules`); `mcp_server` in `sys.modules` is EXPECTED and allowed.

- [ ] **Step 1: Write the test**

`demoflow/tests/test_import_direction.py`:
```python
import re
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "demoflow"
FORBIDDEN = re.compile(r"^\s*(?:import\s+hde\b|from\s+hde\b)", re.MULTILINE)


def test_public_api_does_not_pull_in_hde():
    # Fresh interpreter: importing demoflow's public API must not import hde.
    code = "import demoflow; import sys; assert 'hde' not in sys.modules, sorted(m for m in sys.modules if m=='hde')"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_no_source_file_imports_hde():
    offenders = []
    for py in SRC.rglob("*.py"):
        if FORBIDDEN.search(py.read_text()):
            offenders.append(str(py))
    assert not offenders, f"demoflow source imports hde (forbidden): {offenders}"


def test_actuarial_mcp_server_import_is_allowed():
    # This resolves to actuarial-system's mcp_server, NOT hde's — must succeed.
    from mcp_server.engine.mortality import get_qx  # noqa: F401
```

- [ ] **Step 2: Run the test**

Run: `cd demoflow && uv run pytest tests/test_import_direction.py -v`
Expected: 3 PASS.

- [ ] **Step 3: Commit**

```bash
git add demoflow/tests/test_import_direction.py
git commit -m "test(demoflow): import-direction contract (demoflow never imports hde; mcp_server=actuarial's)"
```

**End of T1a session boundary.** Run `cd demoflow && uv run pytest -q` — all T1a tests green
(probes recorded, loaders fail-loud, junctions typed, import contract enforced) before starting T1b.

## T1b — Cohort engine + calibration gates (Tasks 17–24)

### Task 17: Basis guard (BasisError, if-check, survives `python -O`)

**Files:**
- Create: `demoflow/src/demoflow/cohort/__init__.py`
- Create: `demoflow/src/demoflow/cohort/basis.py`
- Test: `demoflow/tests/test_basis_guard.py`

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_basis_guard.py`:
```python
import subprocess
import sys

import pytest

from demoflow.cohort import basis as B
from demoflow.errors import BasisError


def test_normal_path_sets_qc_basis():
    # US default before set is EXPECTED, not an error; after ensure it echoes QC.
    B.ensure_qc_basis()
    from mcp_server.engine.mortality import active_mortality
    assert active_mortality() == ("CPM2014_combined", "CPM-B")


def test_guard_raises_when_basis_not_qc_and_get_qx_never_called(monkeypatch):
    calls = {"get_qx": 0}
    monkeypatch.setattr(B, "set_active_mortality", lambda *a, **k: None)  # no-op: basis stays US
    monkeypatch.setattr(B, "get_qx", lambda *a, **k: calls.__setitem__("get_qx", calls["get_qx"] + 1))
    with pytest.raises(BasisError):
        B.q_at(75, "M", 2035)
    assert calls["get_qx"] == 0  # guard raised BEFORE any get_qx


def test_guard_survives_dash_O():
    # -O strips asserts; the if-check must still raise. Run in a subprocess under -O.
    script = (
        "import demoflow.cohort.basis as B;"
        "B.set_active_mortality=lambda *a,**k:None;"  # no-op keeps US basis
        "from demoflow.errors import BasisError\n"
        "try:\n"
        "    B.q_at(75,'M',2035); raise SystemExit('NO RAISE')\n"
        "except BasisError:\n"
        "    print('BASISERROR_OK')\n"
    )
    r = subprocess.run([sys.executable, "-O", "-c", script], capture_output=True, text=True)
    assert "BASISERROR_OK" in r.stdout, (r.stdout, r.stderr)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_basis_guard.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.cohort.basis`).

- [ ] **Step 3: Write the implementation**

`demoflow/src/demoflow/cohort/__init__.py`: (empty file)

`demoflow/src/demoflow/cohort/basis.py`:
```python
"""Québec-basis guard (spec §2). The engine DEFAULTS to the US RP2014+MP2021
basis; every demoflow entry point sets the QC basis then CHECKS it echoes,
raising BasisError via an explicit if — NEVER a bare assert (stripped under -O)."""
from mcp_server.engine.mortality import active_mortality, get_qx, set_active_mortality

from demoflow.errors import BasisError

QC_BASIS = ("CPM2014_combined", "CPM-B")


def ensure_qc_basis() -> None:
    set_active_mortality(*QC_BASIS)
    if active_mortality() != QC_BASIS:   # if-check, not assert (codex F7)
        raise BasisError(f"active basis {active_mortality()} is not the Québec basis {QC_BASIS}")


def q_at(age: int, gender: str, year: int) -> float:
    """Guarded q_x: ensures the QC basis, then calls get_qx. Age capped at the
    CPM table max via the engine's own clamp (>=100 verified live)."""
    ensure_qc_basis()
    return get_qx(min(age, 120), gender, year)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_basis_guard.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/cohort/__init__.py demoflow/src/demoflow/cohort/basis.py demoflow/tests/test_basis_guard.py
git commit -m "feat(demoflow): QC mortality-basis guard (BasisError, if-check, -O safe; codex F7)"
```

---

### Task 18: Persons→households initialization (three-bucket per-sex, min-matching, balance gate)

**Files:**
- Create: `demoflow/src/demoflow/cohort/init.py`
- Test: `demoflow/tests/test_init.py`

Folded spec §5 (codex r1/r2/r3/r4-F1): per (age, sex), private-household persons partition
into THREE buckets using SEX-SPECIFIC rates: `Solo_s`, `coupled_s`, `Other_s` (persons living
with others — EXCLUDED from owner-unit stock as presumptive non-maintainers). Couples form by
MINIMUM matching, never an average: `Couple = min(coupled_m, coupled_f)`; the excess `max−min`
routes to `Other` (preserves per-sex person conservation). Balance gate
`|coupled_m − coupled_f| / max ≤ 0.25` (when max>0) → breach = `CalibrationError`. Zero-zero →
`Couple=0`, no ratio, no error.

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_init.py`:
```python
import pytest

from demoflow.cohort.init import initialize_households, match_couples, HouseholdInit
from demoflow.errors import CalibrationError


def _sex(v):  # convenience: same value for M and F
    return {"M": v, "F": v}


def test_match_couples_100_v_80_min_and_excess_to_other():
    # 100 vs 80 coupled -> exactly 80 Couple + 20 excess (never 90 averaged); balance 0.20 <= 0.25.
    couple, excess_m, excess_f = match_couples(100.0, 80.0)
    assert couple == 80.0 and excess_m == 20.0 and excess_f == 0.0


def test_match_couples_20_v_100_balance_breach_raises():
    with pytest.raises(CalibrationError, match="balance"):
        match_couples(20.0, 100.0)   # |80|/100 = 0.8 > 0.25


def test_match_couples_zero_zero_no_ratio_no_error():
    couple, em, ef = match_couples(0.0, 0.0)
    assert couple == 0.0 and em == 0.0 and ef == 0.0


def test_all_coupled_100_100_60pct_ownership():
    # §10 fixture (a): 100 M + 100 F all coupled, 60% ownership -> 60 Couple, 0 Solo, 0 Other.
    h = initialize_households(
        pop_by_sex={"M": 100.0, "F": 100.0},
        living_alone_rate_by_sex=_sex(0.0), couple_share_by_sex=_sex(1.0),
        collective_share=0.0, ownership_rate=0.60,
    )
    assert h.owner_couple == 60.0
    assert h.total_couple == 100.0
    assert h.total_solo_m == 0.0 and h.total_solo_f == 0.0
    assert h.total_other_m == 0.0 and h.total_other_f == 0.0


def test_general_case_three_buckets_and_person_conservation():
    # §10 fixture (b): 200 persons (100 M + 100 F), living_alone 0.25, couple_share 0.80
    # -> 50 Solo + 60 Couple + 30 Other; persons reconcile 50 + 120 + 30 = 200.
    h = initialize_households(
        pop_by_sex={"M": 100.0, "F": 100.0},
        living_alone_rate_by_sex=_sex(0.25), couple_share_by_sex=_sex(0.80),
        collective_share=0.0, ownership_rate=1.0,
    )
    assert h.total_solo_m + h.total_solo_f == pytest.approx(50.0)
    assert h.total_couple == pytest.approx(60.0)
    assert h.total_other_m + h.total_other_f == pytest.approx(30.0)
    persons = h.total_solo_m + h.total_solo_f + 2 * h.total_couple + h.total_other_m + h.total_other_f
    assert persons == pytest.approx(200.0)


def test_collective_share_excluded_first():
    h = initialize_households(
        pop_by_sex={"M": 100.0, "F": 0.0},
        living_alone_rate_by_sex=_sex(1.0), couple_share_by_sex=_sex(1.0),
        collective_share=0.10, ownership_rate=1.0,
    )
    assert h.total_solo_m == 90.0   # 100 * (1-0.10) * 1.0, all solo


def test_female_surplus_with_calibrated_per_sex_rates_balances():
    # 85+ realism: pop_F >> pop_M; correctly-calibrated per-sex couple_share keeps coupled counts
    # balanced (the OLD pooled couple_share=1.0 would have fabricated husbands / breached the gate).
    h = initialize_households(
        pop_by_sex={"M": 100.0, "F": 230.0},
        living_alone_rate_by_sex={"M": 0.34, "F": 0.50},
        couple_share_by_sex={"M": 0.52, "F": 0.30},   # coupled_m=34.32, coupled_f=34.5 -> balance ~0.005
        collective_share=0.0, ownership_rate=1.0,
    )
    assert h.total_couple == pytest.approx(min(100 * 0.66 * 0.52, 230 * 0.50 * 0.30), abs=1e-9)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_init.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.cohort.init`).

- [ ] **Step 3: Write the implementation**

`demoflow/src/demoflow/cohort/init.py`:
```python
"""Persons->households conversion (spec §5, codex r1/r2/r3/r4-F1). Three buckets
per SEX using sex-specific rates; couples by MINIMUM matching (never average);
excess routes to Other; per-sex person conservation; balance gate on the coupled
counts. Ownership rates are HOUSEHOLD-maintainer-denominated -> multiply households."""
import math
from dataclasses import dataclass

from demoflow.errors import CalibrationError

_BALANCE_TOL = 0.25


@dataclass(frozen=True)
class HouseholdInit:
    total_couple: float
    total_solo_m: float
    total_solo_f: float
    total_other_m: float
    total_other_f: float
    owner_couple: float
    owner_solo_m: float
    owner_solo_f: float


def match_couples(coupled_m: float, coupled_f: float) -> tuple[float, float, float]:
    """Return (Couple, excess_m, excess_f). Couple = min; excess = max-min (routes to Other).
    Balance gate |cm-cf|/max <= 0.25 when max>0 (per-sex Census rates should nearly balance)."""
    mx = max(coupled_m, coupled_f)
    if mx > 0.0 and abs(coupled_m - coupled_f) / mx > _BALANCE_TOL:
        raise CalibrationError(
            f"couple balance breach: |{coupled_m} - {coupled_f}| / {mx} > {_BALANCE_TOL} "
            f"(per-sex rate inputs inconsistent)")
    couple = min(coupled_m, coupled_f)
    return couple, coupled_m - couple, coupled_f - couple


def initialize_households(
    pop_by_sex: dict[str, float],
    living_alone_rate_by_sex: dict[str, float],
    couple_share_by_sex: dict[str, float],
    collective_share: float,
    ownership_rate: float,
) -> HouseholdInit:
    eff = {s: pop_by_sex.get(s, 0.0) * (1.0 - collective_share) for s in ("M", "F")}
    solo = {s: eff[s] * living_alone_rate_by_sex[s] for s in ("M", "F")}
    coupled = {s: eff[s] * (1.0 - living_alone_rate_by_sex[s]) * couple_share_by_sex[s] for s in ("M", "F")}
    other_base = {s: eff[s] * (1.0 - living_alone_rate_by_sex[s]) * (1.0 - couple_share_by_sex[s])
                  for s in ("M", "F")}

    couple, excess_m, excess_f = match_couples(coupled["M"], coupled["F"])
    other_m = other_base["M"] + excess_m
    other_f = other_base["F"] + excess_f

    # per-sex person conservation (nothing fabricated/dropped)
    for s in ("M", "F"):
        assert math.isclose(solo[s] + coupled[s] + other_base[s], eff[s], rel_tol=1e-9, abs_tol=1e-9)

    return HouseholdInit(
        total_couple=couple, total_solo_m=solo["M"], total_solo_f=solo["F"],
        total_other_m=other_m, total_other_f=other_f,
        owner_couple=couple * ownership_rate,          # Other EXCLUDED from owner stock
        owner_solo_m=solo["M"] * ownership_rate,
        owner_solo_f=solo["F"] * ownership_rate,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_init.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/cohort/init.py demoflow/tests/test_init.py
git commit -m "feat(demoflow): three-bucket per-sex init + min-matching couples + balance gate (§5 r1-r4-F1)"
```

---

### Task 19: q_live annualization

**Files:**
- Create: `demoflow/src/demoflow/cohort/decrements.py`
- Test: `demoflow/tests/test_q_live.py`

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_q_live.py`:
```python
import pytest

from demoflow.cohort.decrements import annualize_q_live, Q_LIVE_BAND


def test_annualize_cmhc_36pct_5yr_is_about_8_5pct():
    # 1 - (1 - 0.36)^(1/5) ~= 0.0854 (spec §5 / I3)
    assert annualize_q_live(0.36) == pytest.approx(0.0854, abs=1e-3)


def test_annualized_value_in_band():
    q = annualize_q_live(0.36)
    assert Q_LIVE_BAND[0] <= q <= Q_LIVE_BAND[1]   # [0.06, 0.11]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_q_live.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.cohort.decrements`).

- [ ] **Step 3: Write the implementation**

`demoflow/src/demoflow/cohort/decrements.py`:
```python
"""Living-exit calibration + competing-risk partition algebra (spec §5).
q_live is the survivor-conditional living-sale hazard, annualized from CMHC
36%/5yr (75+ QC); the Myers all-cause retention numbers are NEVER a target (I3)."""
from demoflow.errors import CalibrationError

Q_LIVE_BAND = (0.06, 0.11)


def annualize_q_live(five_year_rate: float = 0.36) -> float:
    if not 0.0 <= five_year_rate < 1.0:
        raise CalibrationError(f"five_year_rate out of [0,1): {five_year_rate}")
    return 1.0 - (1.0 - five_year_rate) ** (1.0 / 5.0)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_q_live.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/cohort/decrements.py demoflow/tests/test_q_live.py
git commit -m "feat(demoflow): q_live annualization 1-(1-0.36)^(1/5) with band (spec I3)"
```

---

### Task 20: Competing-risk partition algebra (death first, survivor-conditional, widow retained)

**Files:**
- Modify: `demoflow/src/demoflow/cohort/decrements.py`
- Test: `demoflow/tests/test_partition.py`

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_partition.py`:
```python
import pytest

from demoflow.cohort.decrements import partition_solo, partition_couple
from demoflow.errors import CalibrationError


def test_solo_partition_fixture():
    # spec §5/§10: q_s=0.20, q_live=0.10 -> death 0.20, living-exit 0.08, remain 0.72; sum 1.
    p = partition_solo(0.20, 0.10)
    assert p["death"] == pytest.approx(0.20)
    assert p["living_exit"] == pytest.approx(0.08)
    assert p["remain"] == pytest.approx(0.72)
    assert sum(p.values()) == pytest.approx(1.0)
    assert all(v >= 0 for v in p.values())


def test_couple_partition_sums_to_one_and_widow_retained():
    # death resolves first; living exit survivor-conditional; branches partition to 1.
    p = partition_couple(q_m=0.02, q_f=0.01, q_live=0.10)
    assert sum(p.values()) == pytest.approx(1.0)
    # both-die (estate), widow->Solo_m, widow->Solo_f, living_exit, remain
    assert p["both_die"] == pytest.approx(0.02 * 0.01)
    assert p["widow_to_solo_f"] == pytest.approx(0.02 * (1 - 0.01))   # male dies, female survives
    assert p["widow_to_solo_m"] == pytest.approx(0.01 * (1 - 0.02))   # female dies, male survives
    no_death = (1 - 0.02) * (1 - 0.01)
    assert p["living_exit"] == pytest.approx(no_death * 0.10)
    assert p["remain"] == pytest.approx(no_death * 0.90)
    # widows are RETAINED (own the unit), not counted as exits
    assert p["widow_to_solo_m"] > 0 and p["widow_to_solo_f"] > 0


def test_q_outside_unit_raises():
    with pytest.raises(CalibrationError):
        partition_solo(1.2, 0.10)
    with pytest.raises(CalibrationError):
        partition_couple(q_m=-0.1, q_f=0.01, q_live=0.10)
    with pytest.raises(CalibrationError):
        partition_solo(0.2, 1.5)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_partition.py -v`
Expected: FAIL (`ImportError: cannot import name 'partition_solo'`).

- [ ] **Step 3: Add the implementation to decrements.py**

Append to `demoflow/src/demoflow/cohort/decrements.py`:
```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_partition.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/cohort/decrements.py demoflow/tests/test_partition.py
git commit -m "feat(demoflow): competing-risk partition (death-first, survivor-conditional, widow retained; codex F3)"
```

---

### Task 21: Reconciliation gate ([0.20,0.40] → CalibrationError)

**Files:**
- Create: `demoflow/src/demoflow/cohort/gates.py`
- Test: `demoflow/tests/test_reconciliation_gate.py`

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_reconciliation_gate.py`:
```python
import pytest

from demoflow.cohort.gates import check_reconciliation, RECONCILIATION_BAND
from demoflow.errors import CalibrationError


def test_band_is_myers_widened():
    assert RECONCILIATION_BAND == (0.20, 0.40)


def test_in_band_passes():
    check_reconciliation(0.30)  # no raise


def test_below_band_raises():
    with pytest.raises(CalibrationError, match="reconciliation"):
        check_reconciliation(0.15)


def test_above_band_raises():
    with pytest.raises(CalibrationError, match="reconciliation"):
        check_reconciliation(0.45)


def test_closed_band_endpoints_pass():
    check_reconciliation(0.20)
    check_reconciliation(0.40)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_reconciliation_gate.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.cohort.gates`).

- [ ] **Step 3: Write the implementation**

`demoflow/src/demoflow/cohort/gates.py`:
```python
"""Reconciliation gate (spec §5, codex r9-F4): decade all-cause retention of a 75+
owner cohort must land in [0.20, 0.40] (Myers 0.26-0.31 widened). Outside ->
CalibrationError. Retention is STATE-DEPENDENT, so the cohort composition is PINNED:
the household-state + sex mix the initialization equations produce on the committed
vintage for MTL_RMR (recorded in the oracle fixture, Task 23). This catches GROSS
mortality double-counting; it is a backstop, NOT a proof of exactly-once (that lives
in the stock-flow equation + the oracle-exact mutation test, Task 22)."""
from demoflow.errors import CalibrationError

RECONCILIATION_BAND = (0.20, 0.40)


def check_reconciliation(retention: float) -> None:
    lo, hi = RECONCILIATION_BAND
    if not lo <= retention <= hi:
        raise CalibrationError(
            f"decade reconciliation retention {retention:.4f} outside band {RECONCILIATION_BAND}"
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_reconciliation_gate.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/cohort/gates.py demoflow/tests/test_reconciliation_gate.py
git commit -m "feat(demoflow): reconciliation gate [0.20,0.40] -> CalibrationError (spec §5)"
```

---

### Task 22: Stock-flow roll-forward (band-entry exactly-once) + double-decrement mutation test

**Files:**
- Create: `demoflow/src/demoflow/cohort/rollforward.py`
- Test: `demoflow/tests/test_rollforward.py`

The t→t+1 equation writes every death term exactly once; entrants enter at band-entry only and
stocks then evolve ONLY by our decrements (NEVER re-anchored to ISQ's projected 75+ stocks). The
**exactly-once guarantee is proven by ORACLE EXACTNESS (codex r7-F5), not the envelope:** at low
q_live a doubled decrement retains ≈0.25, still INSIDE [0.20,0.40], so the envelope cannot carry
exactly-once. The mutation test therefore pins the hand-computed values on a flat-q cohort and
asserts that applying the transition twice STRICTLY CHANGES those pinned values (exact inequality);
the reconciliation envelope stays as a GROSS-error backstop only.

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_rollforward.py`:
```python
import pytest

from demoflow.cohort.rollforward import Stock, roll_one_year, roll_cohort_decade
from demoflow.cohort.decrements import annualize_q_live
from demoflow.cohort.gates import check_reconciliation, RECONCILIATION_BAND


def _flat_qx(qm, qf):
    return lambda age, gender, year: qm if gender == "M" else qf


def test_roll_one_year_conserves_mass_and_routes_widows():
    s = Stock(couple=1000.0, solo_m=0.0, solo_f=0.0)
    nxt, exits = roll_one_year(s, age=75, year=2035, q_live=0.10, qx=_flat_qx(0.02, 0.02))
    # widows (one-dies) retained as Solo, NOT exited; both-die + living_exit are exits.
    assert nxt.solo_m == pytest.approx(1000 * 0.02 * 0.98)   # 19.6
    assert nxt.solo_f == pytest.approx(1000 * 0.02 * 0.98)   # 19.6
    assert nxt.couple == pytest.approx(1000 * 0.98 * 0.98 * 0.90)  # 864.36
    total_out = nxt.couple + nxt.solo_m + nxt.solo_f + exits["estate"] + exits["living"]
    assert total_out == pytest.approx(1000.0)


def test_decade_retention_in_band_gross_backstop():
    # ENVELOPE is a gross-error backstop only (NOT the exactly-once proof).
    q_live = annualize_q_live(0.36)   # ~0.0854
    from demoflow.cohort.basis import q_at
    retention = roll_cohort_decade(start_age=75, start_year=2035, q_live=q_live, qx=q_at)
    lo, hi = RECONCILIATION_BAND
    assert lo <= retention <= hi
    check_reconciliation(retention)   # no raise


def test_double_decrement_mutation_changes_pinned_oracle():
    # codex r7-F5: exactly-once is proven by ORACLE EXACTNESS, not the envelope. Flat q -> the
    # correct single transition pins couple=864.36 / owner_units=903.56; applying the transition
    # TWICE (the re-anchor double-count) STRICTLY changes those pinned values -> detectable.
    once, _ = roll_one_year(Stock(couple=1000.0), age=80, year=2040, q_live=0.10, qx=_flat_qx(0.02, 0.02))
    assert once.couple == pytest.approx(864.36) and once.owner_units == pytest.approx(903.56)
    twice, _ = roll_one_year(once, age=80, year=2040, q_live=0.10, qx=_flat_qx(0.02, 0.02))
    assert twice.couple < once.couple                     # exact inequality: couple strictly shrinks
    assert twice.owner_units < once.owner_units           # the pinned oracle CHANGES under the mutation
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_rollforward.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.cohort.rollforward`).

- [ ] **Step 3: Write the implementation**

`demoflow/src/demoflow/cohort/rollforward.py`:
```python
"""Owner-household stock-flow roll-forward (spec §5, I1). t->t+1 equation, every
death term exactly once; band-entry-only entrants; NEVER re-anchored to ISQ 75+
stocks. Reconciliation retention = fraction of an initial 75 owner cohort whose
unit is still owned (remain + widow-retained) after a decade of decrements."""
from dataclasses import dataclass
from typing import Callable

from demoflow.cohort.decrements import partition_couple, partition_solo

QxProvider = Callable[[int, str, int], float]


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
    Solo of the surviving sex (exit-eligible only from the NEXT year)."""
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
                       years: int = 10) -> float:
    """Roll a pure-couple 75 owner cohort a decade; return retained-ownership fraction
    (remain + widow-retained) / initial. Blended-sex couples on one curve (stated §2).
    This feeds the reconciliation ENVELOPE (gross-error backstop); the exactly-once
    guarantee is the oracle-exact mutation test above, not this band."""
    stock = Stock(couple=1000.0)
    initial = stock.owner_units
    for k in range(years):
        stock, _ = roll_one_year(stock, start_age + k, start_year + k, q_live, qx)
    return stock.owner_units / initial
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_rollforward.py -v`
Expected: 3 PASS. (`test_double_decrement_mutation_changes_pinned_oracle` is deterministic — flat
q, exact arithmetic — so it does not depend on the live CPM curve or the envelope margin.)

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/cohort/rollforward.py demoflow/tests/test_rollforward.py
git commit -m "feat(demoflow): stock-flow roll-forward (band-entry once) + oracle-exact mutation (codex F2/r7-F5)"
```

---

### Task 23: 2-cohort / 3-year oracle (widow timing + band-entry-once) + state-mass conservation

**Files:**
- Modify: `demoflow/src/demoflow/cohort/rollforward.py`
- Test: `demoflow/tests/test_cohort_oracle.py`

The fixtures below PIN the per-state retention paths (codex r9-F4): the Couple remain (864.36),
the widowed Solo_m / Solo_f transitions (19.6 each, then their next-year exit eligibility), and the
{remain, widowed, dissolved, exited} mass partition — the state-by-state oracle the reconciliation
gate's pinned MTL_RMR composition (Task 21) relies on.

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_cohort_oracle.py`:
```python
import pytest

from demoflow.cohort.rollforward import Stock, roll_one_year, roll_cohort_multi_year


def _flat_qx(q=0.02):
    return lambda age, gender, year: q


def test_widow_not_exit_eligible_in_transition_year_then_eligible_next():
    # 1000 couples age75, flat q_m=q_f=0.02, q_live=0.10.
    # 2035->2036 transition: widow_to_solo_m = widow_to_solo_f = 1000*0.02*0.98 = 19.6 each.
    # Those 19.6 widows did NOT get q_live in 2035 (widow branch is disjoint from no-death).
    s0 = Stock(couple=1000.0)
    s1, _ = roll_one_year(s0, age=75, year=2035, q_live=0.10, qx=_flat_qx())
    assert s1.solo_m == pytest.approx(19.6)   # FULL 19.6, no q_live applied in transition year
    assert s1.solo_f == pytest.approx(19.6)
    # 2036->2037: the widows are ordinary Solo -> living_exit = 19.6*(1-0.02)*0.10 = 1.9208.
    s2, exits2 = roll_one_year(s1, age=76, year=2036, q_live=0.10, qx=_flat_qx())
    widow_living_exit = 19.6 * (1 - 0.02) * 0.10  # 1.9208
    # solo remain each = 19.6*(1-0.02)*(1-0.10); plus new widows from the 2036 couple block
    assert exits2["living"] > widow_living_exit   # widows now contribute to living exits (eligible)


def test_band_entry_added_exactly_once():
    # entrants: 500 new age-75 couples per year; original 75-cohort ages out.
    # After 1 year, the age-75 slot holds ONLY the entrants (500), never re-anchored/doubled.
    states = roll_cohort_multi_year(
        base={75: Stock(couple=1000.0), 76: Stock(couple=1000.0)},
        entrants_per_year=500.0, start_year=2035, n_years=2, q_live=0.10, qx=_flat_qx(),
    )
    assert states[2036][75].couple == pytest.approx(500.0)   # entrants once
    assert states[2037][75].couple == pytest.approx(500.0)   # entrants once again (new cohort)


def test_state_mass_conservation_every_household_ends_in_one_state():
    s0 = Stock(couple=137.0, solo_m=11.0, solo_f=23.0)
    s1, exits = roll_one_year(s0, age=80, year=2040, q_live=0.09, qx=_flat_qx(0.03))
    total_out = s1.couple + s1.solo_m + s1.solo_f + exits["estate"] + exits["living"]
    assert total_out == pytest.approx(s0.owner_units)   # {remain,widowed,dissolved,exited} partition


def test_100plus_is_absorbing_bucket_accumulates_age_ins():
    # codex r5-F6: age-99 age-ins AND surviving prior 100+ stock BOTH land in age 100,
    # accumulating (never overwritten/reinitialized), each decremented exactly once.
    base = {99: Stock(couple=100.0), 100: Stock(couple=200.0)}
    states = roll_cohort_multi_year(base, entrants_per_year=0.0, start_year=2035, n_years=1,
                                    q_live=0.10, qx=_flat_qx(0.05))
    from_99, _ = roll_one_year(Stock(couple=100.0), age=99, year=2035, q_live=0.10, qx=_flat_qx(0.05))
    from_100, _ = roll_one_year(Stock(couple=200.0), age=100, year=2035, q_live=0.10, qx=_flat_qx(0.05))
    b = states[2036][100]
    assert b.couple == pytest.approx(from_99.couple + from_100.couple)
    assert b.solo_m == pytest.approx(from_99.solo_m + from_100.solo_m)
    assert max(states[2036].keys()) == 100   # age capped at the absorbing bucket


def test_absorbing_bucket_mass_reconciles_over_three_years():
    base = {99: Stock(couple=50.0), 100: Stock(couple=50.0)}
    states = roll_cohort_multi_year(base, entrants_per_year=0.0, start_year=2035, n_years=3,
                                    q_live=0.10, qx=_flat_qx(0.05))
    total = lambda yr: sum(s.owner_units for s in states[yr].values())
    # no entrants; each decrement applied ONCE -> owner units decline monotonically (no re-init inflation)
    assert total(2035) > total(2036) > total(2037) > total(2038)
    assert max(states[2038].keys()) == 100
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_cohort_oracle.py -v`
Expected: FAIL (`ImportError: cannot import name 'roll_cohort_multi_year'`).

- [ ] **Step 3: Add the multi-year/multi-cohort roller (100+ absorbing)**

Append to `demoflow/src/demoflow/cohort/rollforward.py`:
```python
def _add(a: "Stock", b: "Stock") -> "Stock":
    return Stock(a.couple + b.couple, a.solo_m + b.solo_m, a.solo_f + b.solo_f)


def roll_cohort_multi_year(base: dict[int, "Stock"], entrants_per_year: float,
                           start_year: int, n_years: int, q_live: float, qx: QxProvider):
    """Roll an age-indexed set of owner cohorts forward n_years. Each year every cohort
    transitions and ages by one; the 100+ bucket is ABSORBING (codex r5-F6) — the age-99
    age-ins AND the surviving prior 100+ stock BOTH land in age 100 and ACCUMULATE (never
    overwritten/reinitialized). NEW age-75 entrants enter EXACTLY ONCE at band entry (the
    75+ roll has no age-74 cohort, so entrants are the sole age-75 source). Returns
    {year: {age: Stock}}."""
    states: dict[int, dict[int, Stock]] = {start_year: dict(base)}
    for k in range(n_years):
        year = start_year + k
        cur = states[year]
        nxt: dict[int, Stock] = {}
        for age, stock in cur.items():
            rolled, _ = roll_one_year(stock, age, year, q_live, qx)
            dest = min(age + 1, 100)                     # cap into the 100+ absorbing bucket
            nxt[dest] = _add(nxt[dest], rolled) if dest in nxt else rolled
        nxt[75] = Stock(couple=entrants_per_year)        # band-entry: exactly once
        states[year + 1] = nxt
    return states
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_cohort_oracle.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/cohort/rollforward.py demoflow/tests/test_cohort_oracle.py
git commit -m "test(demoflow): 2-cohort/3-year oracle + 100+ absorbing bucket + mass conservation (§10, §8 r5-F6)"
```

---

### Task 24: Transfer-vs-market split (φ_market + estate-lag convolution)

**Files:**
- Create: `demoflow/src/demoflow/cohort/listings.py`
- Test: `demoflow/tests/test_listings.py`

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_listings.py`:
```python
import pytest

from demoflow.cohort.listings import (
    phi_market, market_listings, PHI_VOLUNTARY, ESTATE_EVENTUAL_FRACTION, ESTATE_LAG_YEARS,
)


def test_phi_central_values():
    # RUN CONTRACT central values (codex r8-F1): voluntary 0.9, estate eventual 0.725, L=2.
    assert PHI_VOLUNTARY == 0.9 and 0.7 <= PHI_VOLUNTARY <= 1.0
    assert ESTATE_EVENTUAL_FRACTION == 0.725 and 0.6 <= ESTATE_EVENTUAL_FRACTION <= 0.85
    assert ESTATE_LAG_YEARS == 2 and ESTATE_LAG_YEARS in (1, 2, 3)
    assert phi_market("voluntary") == 0.9


def test_estate_lag_crosses_year_boundary():
    # 100 estate exits in 2034, L=1, fraction 0.75 -> 75 listings in 2035.
    # 40 voluntary exits in 2035 -> 40*0.9 = 36 listings in 2035.
    listings = market_listings(
        voluntary_by_year={2035: 40.0},
        estate_by_year={2034: 100.0},
        lag=1, eventual_fraction=0.75,
    )
    assert listings[2035] == pytest.approx(75.0 + 36.0)   # 111 total in 2035


def test_unknown_cause_raises():
    with pytest.raises(ValueError):
        phi_market("bequest_of_dragons")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_listings.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.cohort.listings`).

- [ ] **Step 3: Write the implementation**

`demoflow/src/demoflow/cohort/listings.py`:
```python
"""Transfer-vs-market split (spec §5): exits carry cause; phi_market(cause) fractions
with estate-lag convolution. Defaults are the RUN-CONTRACT CENTRAL values (codex r8-F1):
voluntary phi 0.9 (band [0.7,1.0]); estate eventual-listing fraction 0.725 (band [0.6,0.85]),
lag L=2 (band [1,3]). Band endpoints enter ONLY the robustness sweep (rank_stable), never the
headline run. A hand-worked fixture may pass explicit non-central params for a pinned example."""
PHI_VOLUNTARY = 0.9
ESTATE_EVENTUAL_FRACTION = 0.725
ESTATE_LAG_YEARS = 2


def phi_market(cause: str) -> float:
    if cause == "voluntary":
        return PHI_VOLUNTARY
    if cause == "estate":
        return ESTATE_EVENTUAL_FRACTION
    raise ValueError(f"unknown exit cause: {cause!r}")


def market_listings(voluntary_by_year: dict[int, float], estate_by_year: dict[int, float],
                    lag: int = ESTATE_LAG_YEARS,
                    eventual_fraction: float = ESTATE_EVENTUAL_FRACTION) -> dict[int, float]:
    """listings[t] = voluntary[t]*phi_voluntary + estate[t-lag]*eventual_fraction."""
    out: dict[int, float] = {}
    for t, v in voluntary_by_year.items():
        out[t] = out.get(t, 0.0) + v * PHI_VOLUNTARY
    for t, e in estate_by_year.items():
        land = t + lag
        out[land] = out.get(land, 0.0) + e * eventual_fraction
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_listings.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/cohort/listings.py demoflow/tests/test_listings.py
git commit -m "feat(demoflow): transfer-vs-market split (phi_market + estate-lag convolution; spec §5)"
```

**End of T1b session boundary.** Run `cd demoflow && uv run pytest -q` — all T1a+T1b green
(cohort engine + competing-risk algebra + calibration gates + listings) before starting T1c.

## T1c — Coarse demand netting → excess-demand → rankings → tripwires → golden artifacts (Tasks 25–30)

### Task 25: Demand side — native formation (under-75 gross) + dimensional immigrant chain

**Files:**
- Create: `demoflow/src/demoflow/demand/__init__.py`
- Create: `demoflow/src/demoflow/demand/formation.py`
- Test: `demoflow/tests/test_demand.py`

Folded spec §6 (codex r2-F2/r4-F5/r6-F1/r6-F2):
- **Native formation DEFINED, disjoint from S (codex r10 explicit boundary):**
  `D_native = max(0, H_res(18,t))×ownership(18) + Σ_{19≤a<75} max(0, H_res(a,t) −
  H_res(a−1,t−1))×ownership(a)` — GROSS under-75 formations only (cohort-followed headship
  gains, floored at 0). ALL 75+ dynamics (dissolution, downsizing, estate) live in S; the age-75
  boundary makes D and S structurally disjoint (a 75+ headship decline must NOT enter D as
  negative formation, or the senior release double-counts). Native's ONLY population input is
  **P_resident** (operand binding — no code path to total ISQ pop; the pipeline enforces it).
- **Immigrant chain is DIMENSIONALLY explicit:** arrivals(persons) × immigrant headship
  (households/person) → immigrant HOUSEHOLDS; then × `p_imm`, where `p_imm = p_nonimm × ratio`
  asserted ∈[0,1]. Persons never multiply a household rate directly.

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_demand.py`:
```python
import pytest

from demoflow.demand.formation import (
    native_formation, immigrant_households, p_imm, immigrant_formation, total_owner_demand,
)
from demoflow.errors import LoaderError


def test_native_formation_gross_under75_gain():
    # H_t(40)=1000*0.5=500; H_tm1(39)=900*0.5=450; gain=50; x ownership 0.6 => 30.
    d = native_formation(
        resident_pop_t={40: 1000.0}, resident_pop_tm1={39: 900.0},
        headship_by_age={39: 0.5, 40: 0.5}, ownership_by_age={40: 0.6},
    )
    assert d == pytest.approx(30.0)


def test_native_ignores_75plus_changes_disjoint_from_S():
    base = dict(resident_pop_t={40: 1000.0}, resident_pop_tm1={39: 900.0},
                headship_by_age={39: 0.5, 40: 0.5, 79: 0.5, 80: 0.5}, ownership_by_age={40: 0.6, 80: 0.6})
    d0 = native_formation(**base)
    # add a 75+ cohort DECLINE (80 falls vs 79): D must be UNCHANGED (75+ dynamics belong to S).
    d1 = native_formation(
        resident_pop_t={40: 1000.0, 80: 500.0}, resident_pop_tm1={39: 900.0, 79: 2000.0},
        headship_by_age=base["headship_by_age"], ownership_by_age=base["ownership_by_age"])
    assert d1 == pytest.approx(d0)


def test_native_floors_negative_gain_at_zero():
    d = native_formation(resident_pop_t={40: 800.0}, resident_pop_tm1={39: 1000.0},
                         headship_by_age={39: 0.5, 40: 0.5}, ownership_by_age={40: 0.6})
    assert d == 0.0


def test_dimensional_headship_50_couples_vs_100_singles_differ():
    # 100 arriving persons as 50 two-person households (headship 0.5) vs 100 one-person (1.0).
    d_couples = immigrant_formation(100.0, immigrant_headship_rate=0.5, p_nonimm=0.6, ratio=1.0)
    d_singles = immigrant_formation(100.0, immigrant_headship_rate=1.0, p_nonimm=0.6, ratio=1.0)
    assert d_couples == pytest.approx(30.0) and d_singles == pytest.approx(60.0)
    assert d_couples != d_singles          # identical D would be the units defect


def test_p_imm_is_product_asserted_in_unit_interval():
    assert p_imm(0.6, 0.62) == pytest.approx(0.372)
    assert p_imm(0.6, 1.2) == pytest.approx(0.72)   # ratio > 1 valid; product still in [0,1]
    with pytest.raises(LoaderError):
        p_imm(0.9, 1.3)                    # 1.17 outside [0,1] -> raise (product binds, not ratio)


def test_native_at_a_min_18_forms_against_zero_prior_no_wraparound():
    # codex r7-F7: at a_min=18 the prior stock is ZERO by equation (never H(17) via wraparound).
    # A huge planted 17-yo prior would leak in only through a negative-index bug -> assert it does NOT.
    d = native_formation(
        resident_pop_t={18: 100.0}, resident_pop_tm1={17: 9999.0},
        headship_by_age={17: 0.5, 18: 0.5}, ownership_by_age={18: 0.6},
    )
    assert d == pytest.approx(100.0 * 0.5 * 0.6)   # 30.0: H(18,t)=50, prior=0 -> gain 50 x 0.6


def test_total_demand_sums():
    assert total_owner_demand(native=30.0, immigrant=30.0) == pytest.approx(60.0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_demand.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.demand.formation`).

- [ ] **Step 3: Write the implementation**

`demoflow/src/demoflow/demand/__init__.py`: (empty file)

`demoflow/src/demoflow/demand/formation.py`:
```python
"""Demand side (spec §6, codex r2-F2/r4-F5/r6-F1/r6-F2). Native formation = GROSS
under-75 cohort-followed headship gains only (75+ dynamics belong to S — structural
D/S disjointness at the age-75 boundary); its ONLY population input is P_resident.
The immigrant chain is dimensionally explicit: persons -> households -> owner demand,
with p_imm = p_nonimm x ratio asserted in [0,1]."""
from demoflow.loaders.validate import assert_fraction

AGE_MIN = 18        # household-formation floor (codex r7-F7 — a−1 must never leave the domain)
AGE_BOUNDARY = 75


def native_formation(resident_pop_t: dict[int, float], resident_pop_tm1: dict[int, float],
                     headship_by_age: dict[int, float], ownership_by_age: dict[int, float]) -> float:
    """D_native = max(0, H_res(18,t))×ownership(18)  +  Σ_{19≤a<75} max(0, H_res(a,t) −
    H_res(a−1,t−1))×ownership(a)  (codex r10 — the explicit a_min=18 boundary term is INCLUDED;
    the earlier strict `a_min < a < 75` form wrongly dropped it). At a_min entrants form against
    ZERO prior stock, by equation, never by array wraparound (r7-F7). `resident_pop_*` is
    P_resident (§6 operand binding) — never total ISQ pop."""
    total = (max(0.0, resident_pop_t.get(AGE_MIN, 0.0) * headship_by_age.get(AGE_MIN, 0.0))
             * ownership_by_age.get(AGE_MIN, 0.0))              # explicit a_min=18 term (zero prior)
    for a in range(AGE_MIN + 1, AGE_BOUNDARY):                  # 19 <= a < 75
        h_t = resident_pop_t.get(a, 0.0) * headship_by_age.get(a, 0.0)
        h_tm1 = resident_pop_tm1.get(a - 1, 0.0) * headship_by_age.get(a - 1, 0.0)
        total += max(0.0, h_t - h_tm1) * ownership_by_age.get(a, 0.0)
    return total


def immigrant_households(arrival_persons: float, immigrant_headship_rate: float) -> float:
    """Persons -> households (households per person). Encodes household size, so 100
    persons as 50 two-person households (rate 0.5) != 100 one-person households (rate 1.0)."""
    return arrival_persons * immigrant_headship_rate


def p_imm(p_nonimm: float, ratio: float) -> float:
    """p_imm(a) = p_nonimm(a) × ratio, asserted ∈ [0,1] (codex r4-F5 — never a bare ratio)."""
    return assert_fraction("p_imm", p_nonimm * ratio)


def immigrant_formation(arrival_persons: float, immigrant_headship_rate: float,
                        p_nonimm: float, ratio: float) -> float:
    return immigrant_households(arrival_persons, immigrant_headship_rate) * p_imm(p_nonimm, ratio)


def total_owner_demand(native: float, immigrant: float) -> float:
    return native + immigrant
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_demand.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/demand/__init__.py demoflow/src/demoflow/demand/formation.py demoflow/tests/test_demand.py
git commit -m "feat(demoflow): native formation (a_min=18, under-75 gross) + dimensional immigrant chain (§6 r2/r4/r6/r7-F)"
```

---

### Task 25b: I2 decomposition + reconciliation gate + operand binding (immigrant-input join rides here)

**Files:**
- Create: `demoflow/src/demoflow/demand/immigrant_inputs.py`
- Create: `demoflow/src/demoflow/demand/i2.py`
- Test: `demoflow/tests/test_i2.py`

Folded spec §6 (codex r5-F3/r5-F4/r6-F1). Two pieces:
1. **Immigrant-input join table** — immigrant headship + immigrant/non-immigrant ownership ratio
   resolve per MODELED geography from an EXPLICIT source table: MTL_RMR/QC_RMR direct; RA members
   → parent-CMA value `borrowed_prior`; HORS_RMR → province-level `borrowed_prior`; an unresolved
   modeled member RAISES (no unstated default).
2. **I2 decomposition** — `P_resident(t) = P_ISQ(t) − Σ_c SurvivingArrivalCohort_c(t)`; a
   reconciliation gate asserts the identity within tolerance (data-side); the operand-binding
   mutation (feeding total ISQ into native formation) is exercised at pipeline level (Task 29).

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_i2.py`:
```python
import pytest

from demoflow.geography import Geography
from demoflow.demand.immigrant_inputs import resolve_immigrant_inputs, ImmigrantInputs
from demoflow.demand.i2 import p_resident, assert_i2_identity, assert_p_resident_nonneg
from demoflow.errors import CalibrationError, LoaderError


def test_join_direct_borrowed_and_raise():
    direct = resolve_immigrant_inputs(Geography.MTL_RMR)
    assert isinstance(direct, ImmigrantInputs) and direct.flag is None
    ra = resolve_immigrant_inputs(Geography.LAVAL_RA13)
    assert ra.flag == "borrowed_prior"                 # parent-CMA borrow
    hors = resolve_immigrant_inputs(Geography.HORS_RMR)
    assert hors.flag == "borrowed_prior"               # province-level borrow


def test_ratio_is_nonneg_finite_not_fraction():
    # codex r7-F8: the ownership ratio can validly exceed 1 (immigrants out-own non-immigrants).
    assert resolve_immigrant_inputs(Geography.QC_RMR).ownership_ratio >= 0.0
    import demoflow.demand.immigrant_inputs as ii
    assert ii._validate_ratio(1.2) == 1.2               # >1 accepted
    with pytest.raises(LoaderError):
        ii._validate_ratio(-0.1)                        # negative -> raise


def test_p_resident_subtracts_surviving_arrivals():
    assert p_resident(p_isq=10_000.0, surviving_arrivals=[300.0, 200.0]) == pytest.approx(9_500.0)


def test_p_resident_nonnegativity_per_cell():
    # codex r7-F3: arrivals exceeding P_ISQ in a cell = CalibrationError BEFORE any consumer.
    assert_p_resident_nonneg(0.0, ctx="cell")           # zero ok
    with pytest.raises(CalibrationError, match="negative|nonneg"):
        assert_p_resident_nonneg(-5.0, ctx="MTL/2035/ref/age40")


def test_i2_identity_gate_passes_on_consistent_and_fails_on_mutation():
    assert_i2_identity(native_input=9_500.0, p_isq=10_000.0, surviving_arrivals=[300.0, 200.0])
    with pytest.raises(CalibrationError, match="I2"):
        assert_i2_identity(native_input=10_000.0, p_isq=10_000.0, surviving_arrivals=[300.0, 200.0])
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_i2.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.demand.immigrant_inputs`).

- [ ] **Step 3: Write the implementations**

`demoflow/src/demoflow/demand/immigrant_inputs.py`:
```python
"""Immigrant-input join table (spec §6, codex r5-F4/r7-F8). Immigrant headship + the
immigrant/non-immigrant ownership RATIO per modeled geography: CMAs direct; RA members
borrow the parent CMA; HORS_RMR borrows province-level; unresolved -> raise. The ratio is
NOT a fraction (it can exceed 1); validated nonneg-finite (the [0,1] constraint binds the
PRODUCT p_imm, §6). HORS_RMR COMPONENT FLOWS (arrivals) resolve three-way at probe P5/P6
(codex r7-F4): (i) compo's own hors-RMR row; else (ii) province compo net of all RMR rows,
reconciliation-checked; else (iii) if UNRESOLVABLE, HORS_RMR is EXCLUDED FROM RANKINGS ENTIRELY
(codex r10 — a supply-side-only ED would contradict the operand binding, the demand equation, AND
the ED contract at once), recorded as a run-level exclusion naming the unresolved input (pipeline
`EXCLUDED_FROM_RANKINGS` → the rankings document's typed `exclusions[]`, Task 29)."""
from dataclasses import dataclass

from demoflow.errors import LoaderError
from demoflow.geography import Geography
from demoflow.loaders.validate import assert_fraction, assert_nonneg_finite

# (immigrant_headship households/person [fraction], immigrant/non-immigrant ownership ratio [nonneg])
_CMA = {
    Geography.MTL_RMR: (0.42, 0.62),
    Geography.QC_RMR: (0.45, 0.70),
}
_PARENT_CMA = {   # RA member -> parent CMA whose value it borrows (borrowed_prior)
    Geography.MTL_ISLAND_RA06: Geography.MTL_RMR,
    Geography.LAVAL_RA13: Geography.MTL_RMR,
    Geography.LANAUDIERE_RA14_PROXY: Geography.MTL_RMR,
    Geography.LAURENTIDES_RA15_PROXY: Geography.MTL_RMR,
    Geography.MONTEREGIE_RA16_PROXY: Geography.MTL_RMR,
}
_PROVINCE = (0.43, 0.66)   # HORS_RMR province-level borrow


@dataclass(frozen=True)
class ImmigrantInputs:
    immigrant_headship: float
    ownership_ratio: float
    flag: str | None = None


def _validate_ratio(ratio: float) -> float:
    return assert_nonneg_finite("immigrant_ownership_ratio", ratio)   # NOT a fraction (r7-F8)


def _make(headship: float, ratio: float, flag: str | None) -> ImmigrantInputs:
    return ImmigrantInputs(assert_fraction("immigrant_headship", headship), _validate_ratio(ratio), flag)


def resolve_immigrant_inputs(geography: Geography) -> ImmigrantInputs:
    if geography in _CMA:
        return _make(*_CMA[geography], flag=None)
    if geography in _PARENT_CMA:
        return _make(*_CMA[_PARENT_CMA[geography]], flag="borrowed_prior")
    if geography is Geography.HORS_RMR:
        return _make(*_PROVINCE, flag="borrowed_prior")
    raise LoaderError(f"no immigrant inputs resolvable for {geography.value} (no unstated default)")
```

`demoflow/src/demoflow/demand/i2.py`:
```python
"""I2 decomposition + reconciliation gate (spec §6, codex r5-F3/r7-F3). P_resident is
P_ISQ minus surviving arrival cohorts; native formation consumes P_resident ONLY. The
gate asserts the identity (data-side); P_resident ≥ 0 is asserted per cell BEFORE any
consumer (arrivals exceeding P_ISQ contradict the scenario population); the operand-
binding mutation runs at the pipeline (Task 29)."""
from demoflow.errors import CalibrationError

_I2_TOL = 1e-6


def p_resident(p_isq: float, surviving_arrivals: list[float]) -> float:
    return p_isq - sum(surviving_arrivals)


def assert_p_resident_nonneg(value: float, ctx: str) -> float:
    """Per-cell nonnegativity (codex r7-F3): the identity is tautological when P_resident is
    DERIVED from it, so a negative residual base must fail LOUD, never flow into formation."""
    if value < 0.0:
        raise CalibrationError(
            f"P_resident negative at {ctx}: {value} — surviving arrivals exceed P_ISQ (assumptions "
            f"contradict the scenario population)")
    return value


def assert_i2_identity(native_input: float, p_isq: float, surviving_arrivals: list[float]) -> None:
    """native_input must equal P_ISQ - Σ surviving arrivals (feeding total P_ISQ -> fail)."""
    expected = p_resident(p_isq, surviving_arrivals)
    if abs(native_input - expected) > _I2_TOL + 1e-9 * abs(expected):
        raise CalibrationError(
            f"I2 double-entry: native formation input {native_input} != P_resident {expected} "
            f"(P_ISQ {p_isq} - arrivals {sum(surviving_arrivals)})")
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_i2.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/demand/immigrant_inputs.py demoflow/src/demoflow/demand/i2.py demoflow/tests/test_i2.py
git commit -m "feat(demoflow): immigrant-input join + I2 decomposition/reconciliation gate (§6 r5-F3/F4,r6-F1)"
```

---

### Task 26: OwnerStock defining equation + excess-demand fraction + hand-worked fixture

**Files:**
- Create: `demoflow/src/demoflow/balance/__init__.py`
- Create: `demoflow/src/demoflow/balance/owner_stock.py`
- Create: `demoflow/src/demoflow/balance/excess_demand.py`
- Test: `demoflow/tests/test_owner_stock.py`
- Test: `demoflow/tests/test_excess_demand.py`

The ED denominator has ONE defining equation (spec §7 codex r3-F3):
`OwnerStock(g,t,s) = Σ_all_ages pop(a,g,t,s) × headship(a) × ownership(a)` — annual re-estimation
from ISQ scenario population with BASE-YEAR Census headship + ownership held constant (PIT-fixed,
labeled assumption). This is a stock LEVEL estimate; ISQ-embedded mortality is correct here and
does not conflict with I1 (which governs the 75+ exit FLOW model only).

- [ ] **Step 1a: Write the OwnerStock failing test**

`demoflow/tests/test_owner_stock.py`:
```python
import pytest

from demoflow.balance.owner_stock import owner_stock


def test_owner_stock_all_age_pit_fixed_equation():
    # OwnerStock = Σ_a pop(a) * headship(a) * ownership(a)
    # 1000*0.6*0.65 + 500*0.7*0.60 = 390 + 210 = 600.
    s = owner_stock(
        pop_by_age={70: 1000.0, 80: 500.0},
        headship_by_age={70: 0.6, 80: 0.7},
        ownership_by_age={70: 0.65, 80: 0.60},
    )
    assert s == pytest.approx(600.0)


def test_owner_stock_ignores_ages_without_rates():
    s = owner_stock(pop_by_age={40: 1000.0}, headship_by_age={}, ownership_by_age={})
    assert s == 0.0
```

- [ ] **Step 1b: Write the excess-demand failing test**

`demoflow/tests/test_excess_demand.py`:
```python
import pytest

from demoflow.balance.excess_demand import excess_demand, MIN_OWNER_STOCK
from demoflow.cohort.listings import market_listings
from demoflow.demand.formation import total_owner_demand
from demoflow.errors import CalibrationError


def test_hand_worked_ed_with_estate_lag_boundary_crossing():
    # ED(g,t,s) = [D - S] / OwnerStock, all annual, household-denominated (spec §7).
    # D = native 200 + immigrant 50 = 250.
    # S = voluntary(2035)=40*0.9=36  +  estate(2034)=100 lists in 2035 at 0.75 = 75  => 111.
    #     (estate-lag boundary crossing: 2034 death -> 2035 listing; explicit non-central params).
    # OwnerStock(2035) = 5000.  ED = (250 - 111) / 5000 = 139/5000 = 0.0278.
    D = total_owner_demand(native=200.0, immigrant=50.0)
    S = market_listings(voluntary_by_year={2035: 40.0}, estate_by_year={2034: 100.0},
                        lag=1, eventual_fraction=0.75)[2035]
    assert S == pytest.approx(111.0)
    ed = excess_demand(D=D, S=S, owner_stock=5000.0)
    assert ed == pytest.approx(0.0278, abs=1e-6)


def test_owner_stock_numeric_boundary_999_1000_1001():
    # codex r9-F5: OwnerStock < 1,000 households raises (never leave "near-zero" to taste).
    assert MIN_OWNER_STOCK == 1000.0
    with pytest.raises(CalibrationError, match="1000|OwnerStock"):
        excess_demand(D=10.0, S=5.0, owner_stock=999.0)
    excess_demand(D=10.0, S=5.0, owner_stock=1000.0)    # boundary: allowed (>= 1000)
    excess_demand(D=10.0, S=5.0, owner_stock=1001.0)
```

- [ ] **Step 2: Run to verify both fail**

Run: `cd demoflow && uv run pytest tests/test_owner_stock.py tests/test_excess_demand.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.balance.owner_stock` / `.excess_demand`).

- [ ] **Step 3: Write the implementations**

`demoflow/src/demoflow/balance/__init__.py`: (empty file)

`demoflow/src/demoflow/balance/owner_stock.py`:
```python
"""OwnerStock defining equation (spec §7, codex r3-F3). ONE equation for the ED
denominator: annual re-estimation from ISQ scenario population with BASE-YEAR Census
headship + ownership held constant (PIT-fixed). Stock LEVEL — ISQ-embedded mortality
is correct here; I1 governs only the 75+ exit FLOW model."""


def owner_stock(pop_by_age: dict[int, float], headship_by_age: dict[int, float],
                ownership_by_age: dict[int, float]) -> float:
    return sum(
        pop * headship_by_age.get(a, 0.0) * ownership_by_age.get(a, 0.0)
        for a, pop in pop_by_age.items()
    )
```

`demoflow/src/demoflow/balance/excess_demand.py`:
```python
"""Excess-demand fraction (spec §7, codex F4). All terms annual, household-
denominated, per (geography g, year t, scenario s):

    ED(g,t,s) = [ D(g,t,s) - S(g,t,s) ] / OwnerStock(g,t,s)

    D = native owner-household formation + immigrant-cohort formation   (demand/formation.py)
    S = sum_cause exits(cause) * phi_market(cause), estate lagged L      (cohort/listings.py)
    OwnerStock = the §7 defining equation                               (balance/owner_stock.py)

ED is scale-invariant (households/households). Denominator guard has a NUMERIC boundary
(codex r9-F5): OwnerStock < 1,000 households -> raise (no modeled geography legitimately
carries fewer; never leave "near-zero" to implementation taste, never emit an unbounded
fraction). Tranche 1 stops at the raw fraction; the ED->drift mapping (beta) is Tranche 2."""
from demoflow.errors import CalibrationError

MIN_OWNER_STOCK = 1000.0


def excess_demand(D: float, S: float, owner_stock: float) -> float:
    if owner_stock < MIN_OWNER_STOCK:
        raise CalibrationError(
            f"OwnerStock {owner_stock} < {MIN_OWNER_STOCK} households — no modeled geography "
            f"legitimately carries fewer (denominator guard)")
    return (D - S) / owner_stock
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd demoflow && uv run pytest tests/test_owner_stock.py tests/test_excess_demand.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/balance/__init__.py demoflow/src/demoflow/balance/owner_stock.py demoflow/src/demoflow/balance/excess_demand.py demoflow/tests/test_owner_stock.py demoflow/tests/test_excess_demand.py
git commit -m "feat(demoflow): OwnerStock defining equation + excess-demand fraction + <1000 guard (§7 r3-F3/r9-F5, codex F4)"
```

---

### Task 27: Rankings table (scenario-named fans, closed flags enum, row allowlist)

**Files:**
- Create: `demoflow/src/demoflow/output/__init__.py`
- Create: `demoflow/src/demoflow/output/rankings.py`
- Test: `demoflow/tests/test_rankings.py`

Collapse rule (codex F4): rank by MEAN ED over horizon years under the REFERENCE scenario,
ASCENDING (most negative = rank 1); ties break by the LOW-scenario (Faible) mean, then enum order.
**Scenario-NAMED fan fields (codex r6-F6/r8-F4 — the old min/max sentence is GONE from the spec):**
`mean_ed_low` = the Faible (D2026 / `Scenario.LOW`) mean, `mean_ed_high` = the Fort (E2026 /
`Scenario.HIGH`) mean — scenario identity, NOT min/max; they can CROSS numerically; any min/max
envelope is display-derived, never stored. **Row allowlist + closed flags enum + typed rank_stable
(codex r5-F5/r6-F4/r8-F1/r9-F1):** the emitted rankings row = {geography, mean_ed_reference,
mean_ed_low, mean_ed_high, rank, **rank_stable** (TYPED bool — the robustness-sweep verdict, never
a flag string), flags[]}; `flags[]` is the CLOSED enum {borrowed_prior, ra_proxy} — no free-text; a
smuggled `crash_probability` (field OR flag token) is rejected, independent of the golden. (Ranking
temporal DOMAIN = projected years only + the identity envelope are wired in Task 29.)

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_rankings.py`:
```python
import pytest

from demoflow.geography import Geography, Scenario
from demoflow.output.rankings import (
    rank_geographies, refuse_cross_vintage, ranking_row, assert_rankings_row_valid,
    RANKINGS_ROW_FIELDS, RANKING_FLAGS_ALLOWED, GeoRanking,
)
from demoflow.errors import CalibrationError


def _ed(ref, low, high):
    return {Scenario.REFERENCE: ref, Scenario.LOW: low, Scenario.HIGH: high}


def test_unique_ordering_with_exact_tie():
    ed = {
        Geography.MTL_RMR: _ed([-0.05, -0.03], [-0.08, -0.06], [-0.02, 0.00]),   # ref -0.04, Faible -0.07
        Geography.QC_RMR: _ed([-0.04, -0.04], [-0.05, -0.05], [-0.03, -0.01]),    # ref -0.04 (tie), Faible -0.05
        Geography.LANAUDIERE_RA14_PROXY: _ed([-0.03, -0.01], [-0.07, -0.05], [0.04, 0.02]),  # ref -0.02
        Geography.LAVAL_RA13: _ed([0.01, -0.01], [-0.02, -0.04], [0.03, 0.01]),   # ref 0.00
    }
    ranked = rank_geographies(ed)
    assert [r.geography for r in ranked] == [
        Geography.MTL_RMR,               # tie at -0.04 wins on Faible mean -0.07 < -0.05
        Geography.QC_RMR,
        Geography.LANAUDIERE_RA14_PROXY,
        Geography.LAVAL_RA13,
    ]
    assert [r.rank for r in ranked] == [1, 2, 3, 4]


def test_scenario_named_fan_fields_can_cross():
    # codex r6-F6: mean_ed_low is the FAIBLE mean, mean_ed_high the FORT mean — NOT min/max.
    # Faible +0.02, Fort -0.03 -> mean_ed_low (0.02) > mean_ed_high (-0.03): a legitimate crossing.
    ed = {Geography.MTL_RMR: _ed([-0.01], [0.02], [-0.03])}
    r = rank_geographies(ed)[0]
    assert r.mean_ed_low == pytest.approx(0.02)     # Faible, whatever the numeric order
    assert r.mean_ed_high == pytest.approx(-0.03)   # Fort
    assert r.mean_ed_low > r.mean_ed_high           # scenarios crossed; fields are scenario-named


def test_enum_order_final_tiebreak():
    ed = {
        Geography.QC_RMR: _ed([-0.04], [-0.05], [-0.03]),
        Geography.MTL_RMR: _ed([-0.04], [-0.05], [-0.03]),
    }
    assert [r.geography for r in rank_geographies(ed)] == [Geography.MTL_RMR, Geography.QC_RMR]


def test_ra_proxy_flagged_and_in_closed_enum():
    r = rank_geographies({Geography.LANAUDIERE_RA14_PROXY: _ed([-0.02], [-0.03], [-0.01])})[0]
    assert "ra_proxy" in r.flags and set(r.flags) <= RANKING_FLAGS_ALLOWED


def test_cross_vintage_comparison_refused():
    with pytest.raises(CalibrationError, match="vintage"):
        refuse_cross_vintage({"vintageA", "vintageB"})
    refuse_cross_vintage({"vintageA"})


def test_row_allowlist_exact_and_flag_enum_reject_crash_probability():
    r = rank_geographies({Geography.MTL_RMR: _ed([-0.02], [-0.03], [-0.01])})[0]
    row = ranking_row(r)
    assert set(row) == RANKINGS_ROW_FIELDS
    assert_rankings_row_valid(row)                          # clean row: no raise
    with pytest.raises(ValueError, match="allowlist"):      # RED: extra forbidden field
        assert_rankings_row_valid({**row, "crash_probability": 0.35})
    with pytest.raises(ValueError, match="flag"):           # RED: smuggled through flags[]
        assert_rankings_row_valid({**row, "flags": ["crash_probability=0.35"]})


def test_rank_stable_is_typed_bool_not_a_flag_string():
    # codex r8-F1/r9-F1: the robustness-sweep verdict has a TYPED schema home, never a flag string.
    r = rank_geographies({Geography.MTL_RMR: _ed([-0.02], [-0.03], [-0.01])},
                         rank_stable={Geography.MTL_RMR: False})[0]
    assert r.rank_stable is False
    row = ranking_row(r)
    assert row["rank_stable"] is False and isinstance(row["rank_stable"], bool)


def test_ordering_reverses_all_years_vs_projected_only():
    # codex r8-F3: the ranking domain (projected years only) is load-bearing — a pair whose order
    # REVERSES between an all-years average and a projected-only average. rank_geographies averages
    # whatever series it is given; the pipeline supplies the projected-only slice.
    all_years = {   # includes leading "estimation-year" values that pull the mean
        Geography.MTL_RMR: _ed([0.10, -0.06], [0.0], [0.0]),   # all-years ref mean +0.02
        Geography.QC_RMR: _ed([-0.01, -0.02], [0.0], [0.0]),   # all-years ref mean -0.015 -> QC rank 1
    }
    projected_only = {   # only the later projected values
        Geography.MTL_RMR: _ed([-0.06], [0.0], [0.0]),          # proj ref mean -0.06 -> MTL rank 1
        Geography.QC_RMR: _ed([-0.02], [0.0], [0.0]),           # proj ref mean -0.02
    }
    order_all = [r.geography for r in rank_geographies(all_years)]
    order_proj = [r.geography for r in rank_geographies(projected_only)]
    assert order_all[0] is Geography.QC_RMR and order_proj[0] is Geography.MTL_RMR   # reversed
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_rankings.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.output.rankings`).

- [ ] **Step 3: Write the implementation**

`demoflow/src/demoflow/output/__init__.py`: (empty file)

`demoflow/src/demoflow/output/rankings.py`:
```python
"""Rankings table (spec §7b, codex F4/r5-F5/r6-F4/r6-F6). Deterministic ordering from a
multi-year x 3-scenario ED trajectory. Fan fields are SCENARIO-NAMED (Faible/Fort), not
min/max. The emitted row obeys a closed field allowlist and a closed flags enum — no
free-text channel for the prohibited quantities. RA14/15/16 carry `ra_proxy`."""
from dataclasses import dataclass, field

from demoflow.errors import CalibrationError
from demoflow.geography import Geography, RA_PROXY_MEMBERS, Scenario

_ENUM_ORDER = {g: i for i, g in enumerate(Geography)}

RANKINGS_ROW_FIELDS = frozenset(
    {"geography", "mean_ed_reference", "mean_ed_low", "mean_ed_high", "rank", "rank_stable", "flags"})
RANKING_FLAGS_ALLOWED = frozenset({"borrowed_prior", "ra_proxy"})


@dataclass(frozen=True)
class GeoRanking:
    rank: int
    geography: Geography
    mean_ed_reference: float
    mean_ed_low: float        # Faible (D2026 / Scenario.LOW) mean — scenario-named, not min
    mean_ed_high: float       # Fort   (E2026 / Scenario.HIGH) mean — scenario-named, not max
    rank_stable: bool = True  # robustness-sweep verdict (codex r8-F1/r9-F1) — TYPED, never a flag string
    flags: list[str] = field(default_factory=list)


def _mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs)


def refuse_cross_vintage(vintages: set[str]) -> None:
    """Single run only (one data vintage / assumptions_hash); cross-vintage refused (§7b)."""
    if len(vintages) > 1:
        raise CalibrationError(f"cross-vintage ranking refused: {sorted(vintages)}")


def rank_geographies(ed: dict[Geography, dict[Scenario, list[float]]],
                     borrowed: set[Geography] | None = None,
                     rank_stable: dict[Geography, bool] | None = None) -> list[GeoRanking]:
    borrowed = borrowed or set()
    rank_stable = rank_stable or {}
    rows = []
    for geo, by_scen in ed.items():
        rows.append((
            geo,
            _mean(by_scen[Scenario.REFERENCE]),
            _mean(by_scen[Scenario.LOW]),      # Faible
            _mean(by_scen[Scenario.HIGH]),     # Fort
        ))
    # ascending by (ref mean, Faible mean, enum order): most negative ref ED = rank 1.
    rows.sort(key=lambda r: (r[1], r[2], _ENUM_ORDER[r[0]]))
    out = []
    for i, (geo, mref, mlow, mhigh) in enumerate(rows, start=1):
        flags = []
        if geo in RA_PROXY_MEMBERS:
            flags.append("ra_proxy")
        if geo in borrowed:
            flags.append("borrowed_prior")
        out.append(GeoRanking(rank=i, geography=geo, mean_ed_reference=mref, mean_ed_low=mlow,
                              mean_ed_high=mhigh, rank_stable=rank_stable.get(geo, True), flags=flags))
    return out


def ranking_row(gr: GeoRanking) -> dict:
    """The emitted (serialized) rankings row — geography as string, flags as a list."""
    return {"rank": gr.rank, "geography": gr.geography.value,
            "mean_ed_reference": gr.mean_ed_reference, "mean_ed_low": gr.mean_ed_low,
            "mean_ed_high": gr.mean_ed_high, "rank_stable": gr.rank_stable, "flags": list(gr.flags)}


def assert_rankings_row_valid(row: dict) -> None:
    """Contract test hook: field set == allowlist AND every flag in the closed enum."""
    if set(row) != set(RANKINGS_ROW_FIELDS):
        raise ValueError(f"rankings row fields {sorted(row)} != allowlist {sorted(RANKINGS_ROW_FIELDS)}")
    bad = [f for f in row.get("flags", []) if f not in RANKING_FLAGS_ALLOWED]
    if bad:
        raise ValueError(f"rankings flag(s) outside closed enum {sorted(RANKING_FLAGS_ALLOWED)}: {bad}")
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_rankings.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/output/__init__.py demoflow/src/demoflow/output/rankings.py demoflow/tests/test_rankings.py
git commit -m "feat(demoflow): rankings scenario-named fans + closed flags enum + typed rank_stable + row allowlist (§7b r5-F5,r6-F4,r6-F6,r8-F1,r9-F1)"
```

---

### Task 28: Tripwire baselines (fail-safe gate: OK / CROSSED / UNKNOWN)

**Files:**
- Create: `demoflow/src/demoflow/output/tripwires.py`
- Test: `demoflow/tests/test_tripwires.py`

Fail-safe verification gate (spec §7c, codex r2-F4/r3-F4/r3-F5/r6-F4/r7-F1/r7-F2/r8-F2). Per-indicator
status ∈ {OK, CROSSED, UNKNOWN}; the UNKNOWN `reason` is a CLOSED machine-token enum (no free-text).
`source` is BOUND to a CODE-owned registry (indicator → declared source string; the record must
equal it exactly — REQUIRED_INDICATORS derives from that registry). Registry completeness (empty /
missing / duplicate) → nonzero. Value integrity (NaN/±Inf/non-numeric, future `as_of`, inverted
band) → UNKNOWN, never within-band. **UNKNOWN-branch nullability:** `current_value` + `as_of` are
NULL exactly for reason ∈ {source_unavailable, operator_input_missing, missing_indicator,
non_finite} (a non_finite raw value goes to the run log, never the JSON); every other status
requires them non-null. Record allowlist {indicator, current_value, source, as_of, band_low,
band_high, status, reason?} rejects a smuggled `crash_probability` (field, reason, OR source). Exit
0 only when every code-required indicator is present exactly once, finite, fresh, well-banded, OK.

- [ ] **Step 1: Write the failing test (RED includes every false-clean case)**

`demoflow/tests/test_tripwires.py`:
```python
import math

import pytest

from demoflow.output.tripwires import (
    Status, SourceKind, Reason, TripwireSpec, TripwireResult, REQUIRED_INDICATORS,
    TRIPWIRE_RECORD_REQUIRED, evaluate_indicator, check_registry, exit_code,
    tripwire_record, assert_tripwire_record_valid,
)


def _spec(**kw):
    base = dict(indicator="pr_landings_annual", band_low=40000.0, band_high=50000.0, as_of=2026,
                freshness_years=1, source_kind=SourceKind.WIRED)
    base.update(kw)
    return TripwireSpec(**base)


def test_within_band_and_fresh_is_ok():
    assert evaluate_indicator(_spec(), 45000, available=True, now=2026).status is Status.OK


def test_stale_is_unknown_with_closed_reason():
    r = evaluate_indicator(_spec(as_of=2023), 45000, available=True, now=2026)
    assert r.status is Status.UNKNOWN and r.reason is Reason.STALE


def test_unavailable_is_unknown_source_unavailable():
    r = evaluate_indicator(_spec(), None, available=False, now=2026)
    assert r.status is Status.UNKNOWN and r.reason is Reason.SOURCE_UNAVAILABLE


def test_operator_input_missing_is_unknown():
    r = evaluate_indicator(_spec(source_kind=SourceKind.OPERATOR_SUPPLIED), None, available=True, now=2026)
    assert r.status is Status.UNKNOWN and r.reason is Reason.OPERATOR_INPUT_MISSING


def test_non_finite_value_is_unknown_and_current_value_null():   # RED value integrity + r8-F2
    for bad in (math.nan, math.inf, "n/a"):
        r = evaluate_indicator(_spec(), bad, available=True, now=2026)
        assert r.status is Status.UNKNOWN and r.reason is Reason.NON_FINITE
        assert r.current_value is None and r.as_of is None   # raw value -> run log, not the record


def test_future_as_of_is_unknown():
    r = evaluate_indicator(_spec(as_of=2030), 45000, available=True, now=2026)
    assert r.status is Status.UNKNOWN and r.reason is Reason.FUTURE_AS_OF


def test_inverted_band_is_unknown():
    r = evaluate_indicator(_spec(band_low=50000.0, band_high=40000.0), 45000, available=True, now=2026)
    assert r.status is Status.UNKNOWN and r.reason is Reason.MALFORMED_BAND


def test_closed_band_endpoints_are_crossed():
    assert evaluate_indicator(_spec(), 40000, available=True, now=2026).status is Status.CROSSED
    assert evaluate_indicator(_spec(), 50000, available=True, now=2026).status is Status.CROSSED


def test_registry_completeness_empty_missing_duplicate():
    from demoflow.errors import LoaderError
    with pytest.raises(LoaderError, match="empty"):              # codex r10: empty = RUN-level terminal
        check_registry([])
    missing = check_registry(["pr_landings_annual"])            # far short of the required set
    assert any(r.reason is Reason.MISSING_INDICATOR for r in missing) and exit_code(missing) != 0
    dup = check_registry(sorted(REQUIRED_INDICATORS) + ["pr_landings_annual"])
    assert any(r.reason is Reason.DUPLICATE_INDICATOR for r in dup) and exit_code(dup) != 0
    complete = check_registry(sorted(REQUIRED_INDICATORS))
    assert complete == []                                      # no completeness violations


def test_exit_code_zero_only_when_all_ok():
    ok = evaluate_indicator(_spec(), 45000, available=True, now=2026)
    crossed = evaluate_indicator(_spec(), 60000, available=True, now=2026)
    unknown = evaluate_indicator(_spec(), None, available=False, now=2026)
    assert exit_code([ok]) == 0 and exit_code([ok, crossed]) != 0 and exit_code([ok, unknown]) != 0


def test_record_allowlist_and_reason_enum_reject_crash_probability():
    ok = evaluate_indicator(_spec(), 45000, available=True, now=2026)
    rec = tripwire_record(ok)
    assert TRIPWIRE_RECORD_REQUIRED <= set(rec)
    assert_tripwire_record_valid(rec)                         # clean: no raise
    with pytest.raises(ValueError, match="allowlist"):        # RED: forbidden extra field
        assert_tripwire_record_valid({**rec, "crash_probability": 0.35})
    with pytest.raises(ValueError, match="reason"):           # RED: smuggled through reason
        assert_tripwire_record_valid({**rec, "reason": "crash_probability=0.35"})


def test_source_bound_to_code_owned_registry():
    from demoflow.output.tripwires import SOURCE_REGISTRY
    rec = tripwire_record(evaluate_indicator(_spec(), 45000, available=True, now=2026))
    assert rec["source"] == SOURCE_REGISTRY["pr_landings_annual"]   # declared string, not a SourceKind
    with pytest.raises(ValueError, match="source"):                # RED: smuggled source content
        assert_tripwire_record_valid({**rec, "source": "crash_probability=0.35"})


def test_unknown_branch_nullability_contract():
    ok = tripwire_record(evaluate_indicator(_spec(), 45000, available=True, now=2026))
    assert ok["current_value"] is not None and ok["as_of"] is not None
    assert_tripwire_record_valid(ok)
    with pytest.raises(ValueError, match="non-null"):          # OK record cannot null its value
        assert_tripwire_record_valid({**ok, "current_value": None})

    unavail = tripwire_record(evaluate_indicator(_spec(), None, available=False, now=2026))
    assert unavail["current_value"] is None and unavail["as_of"] is None   # nullable-reason branch
    assert_tripwire_record_valid(unavail)
    with pytest.raises(ValueError, match="NULL"):              # nullable-reason record cannot carry a value
        assert_tripwire_record_valid({**unavail, "current_value": 45000.0})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_tripwires.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.output.tripwires`).

- [ ] **Step 3: Write the implementation**

`demoflow/src/demoflow/output/tripwires.py`:
```python
"""Tripwire baselines (spec §7c). Fail-safe gate: REFUSES (UNKNOWN) when it cannot
verify; closed reason enum + `source`-bound-to-registry + record allowlist close the
string side-channel; the required set is CODE-owned (defeats co-deletion). Exit 0 iff
every required indicator is present-once, finite, fresh, well-banded, OK."""
import math
from dataclasses import dataclass
from enum import Enum

from demoflow.errors import LoaderError


class Status(str, Enum):
    OK = "OK"
    CROSSED = "CROSSED"
    UNKNOWN = "UNKNOWN"


class SourceKind(str, Enum):
    WIRED = "wired"
    OPERATOR_SUPPLIED = "operator_supplied"


class Reason(str, Enum):   # CLOSED machine-token enum — no free-text (codex r6-F4)
    STALE = "stale"
    SOURCE_UNAVAILABLE = "source_unavailable"
    OPERATOR_INPUT_MISSING = "operator_input_missing"
    NON_FINITE = "non_finite"
    MALFORMED_BAND = "malformed_band"
    FUTURE_AS_OF = "future_as_of"
    MISSING_INDICATOR = "missing_indicator"
    DUPLICATE_INDICATOR = "duplicate_indicator"
    # codex r10: `empty_registry` is NOT a per-indicator reason — an empty baseline is a RUN-level
    # terminal error (check_registry raises; NO artifact is emitted; the run exits nonzero).


# CODE-owned registry (spec §7c, codex r7-F1): indicator -> its DECLARED source string. The
# emitted record's `source` must equal this exactly (no smuggled content). REQUIRED_INDICATORS
# derives from it — one source of truth, NOT in the baseline file it validates.
SOURCE_REGISTRY = {
    "pr_landings_annual": "IRCC PR admissions by CMA (open.canada.ca monthly CSV)",
    "temp_resident_stock": "StatCan NPR estimates 17-10-0121 family (or IRCC TR tables)",
    "isq_edition_watch": "ISQ Perspectives demographiques edition watch (slug/pin)",
    "registre_foncier_volume": "Registre foncier monthly transfer counts (operator-supplied)",
    "cmhc_senior_sale_5yr": "CMHC senior-sale rate refresh (operator-supplied)",
    "natural_increase_sign": "ISQ compo natural-increase sign, annual release (operator-supplied)",
}
REQUIRED_INDICATORS = frozenset(SOURCE_REGISTRY)

# UNKNOWN-branch nullability (codex r7-F2/r8-F2): current_value + as_of are NULL exactly for these
# reasons (no honest measurement; a non_finite raw value goes to the run log, never the JSON).
NULLABLE_REASONS = frozenset({
    Reason.SOURCE_UNAVAILABLE, Reason.OPERATOR_INPUT_MISSING, Reason.MISSING_INDICATOR, Reason.NON_FINITE})

TRIPWIRE_RECORD_REQUIRED = frozenset(
    {"indicator", "current_value", "source", "as_of", "band_low", "band_high", "status"})
_OPTIONAL = {"reason"}


@dataclass(frozen=True)
class TripwireSpec:
    indicator: str
    band_low: float
    band_high: float
    as_of: int
    freshness_years: int
    source_kind: SourceKind   # coverage declaration (wired/operator) — internal, NOT emitted


@dataclass(frozen=True)
class TripwireResult:
    indicator: str
    current_value: float | None
    source: str               # DECLARED source string (bound to SOURCE_REGISTRY), never SourceKind
    as_of: int | None
    band_low: float
    band_high: float
    status: Status
    reason: Reason | None = None


def _src(indicator: str) -> str:
    return SOURCE_REGISTRY.get(indicator, "<unregistered>")


def _unknown_nullable(spec: TripwireSpec, reason: Reason) -> TripwireResult:
    # nullable-reason branch: no honest measurement -> current_value AND as_of null.
    return TripwireResult(spec.indicator, None, _src(spec.indicator), None,
                          spec.band_low, spec.band_high, Status.UNKNOWN, reason)


def _unknown_measured(spec: TripwireSpec, v: float, reason: Reason) -> TripwireResult:
    # a real (finite) measurement exists but is stale/future/malformed -> keep value + as_of.
    return TripwireResult(spec.indicator, v, _src(spec.indicator), spec.as_of,
                          spec.band_low, spec.band_high, Status.UNKNOWN, reason)


def evaluate_indicator(spec: TripwireSpec, current_value, available: bool, now: int) -> TripwireResult:
    if not available:
        return _unknown_nullable(spec, Reason.SOURCE_UNAVAILABLE)
    if current_value is None:
        return _unknown_nullable(spec, Reason.OPERATOR_INPUT_MISSING)
    try:
        v = float(current_value)
        if not math.isfinite(v):
            raise ValueError
    except (TypeError, ValueError):
        return _unknown_nullable(spec, Reason.NON_FINITE)   # raw value -> run log, NEVER the JSON
    if spec.as_of > now:
        return _unknown_measured(spec, v, Reason.FUTURE_AS_OF)
    if spec.band_low > spec.band_high:
        return _unknown_measured(spec, v, Reason.MALFORMED_BAND)
    if now - spec.as_of > spec.freshness_years:
        return _unknown_measured(spec, v, Reason.STALE)
    status = Status.CROSSED if (v <= spec.band_low or v >= spec.band_high) else Status.OK
    return TripwireResult(spec.indicator, v, _src(spec.indicator), spec.as_of,
                          spec.band_low, spec.band_high, status, None)


def check_registry(indicators: list[str], required: frozenset[str] = REQUIRED_INDICATORS) -> list[TripwireResult]:
    """Synthetic UNKNOWN results for completeness violations (empty/missing/duplicate) — drive the
    EXIT CODE (not emitted as JSON records in the normal path). Empty list => registry complete."""
    out: list[TripwireResult] = []
    if not indicators:
        # RUN-level terminal (codex r10): no artifact emitted; the run exits nonzero.
        raise LoaderError("empty tripwire registry — NO artifact emitted, run exits nonzero")
    seen: set[str] = set()
    for name in indicators:
        if name in seen:
            out.append(TripwireResult(name, None, _src(name), None, 0.0, 0.0,
                                      Status.UNKNOWN, Reason.DUPLICATE_INDICATOR))
        seen.add(name)
    for missing in sorted(required - set(indicators)):
        out.append(TripwireResult(missing, None, _src(missing), None, 0.0, 0.0,
                                   Status.UNKNOWN, Reason.MISSING_INDICATOR))
    return out


def exit_code(results: list[TripwireResult]) -> int:
    return 0 if results and all(r.status is Status.OK for r in results) else 1


def tripwire_record(r: TripwireResult) -> dict:
    rec = {"indicator": r.indicator, "current_value": r.current_value, "source": r.source,
           "as_of": r.as_of, "band_low": r.band_low, "band_high": r.band_high, "status": r.status.value}
    if r.reason is not None:
        rec["reason"] = r.reason.value
    return rec


def assert_tripwire_record_valid(record: dict) -> None:
    """Contract: exact allowlist; reason in the closed enum; `source` == the registry-declared
    string; UNKNOWN-branch nullability (current_value/as_of null IFF a nullable reason)."""
    extra = set(record) - (set(TRIPWIRE_RECORD_REQUIRED) | _OPTIONAL)
    if extra or not set(TRIPWIRE_RECORD_REQUIRED) <= set(record):
        raise ValueError(f"tripwire record fields {sorted(record)} violate allowlist "
                         f"{sorted(TRIPWIRE_RECORD_REQUIRED)}(+reason?); extra={sorted(extra)}")
    reason = record.get("reason")
    if reason is not None and reason not in {r.value for r in Reason}:
        raise ValueError(f"tripwire reason {record['reason']!r} outside closed enum "
                         f"{sorted(r.value for r in Reason)}")
    ind = record["indicator"]
    if ind in SOURCE_REGISTRY and record["source"] != SOURCE_REGISTRY[ind]:
        raise ValueError(f"tripwire source {record['source']!r} != registry-declared "
                         f"{SOURCE_REGISTRY[ind]!r} for {ind}")
    nullable = (record["status"] == Status.UNKNOWN.value
                and reason in {r.value for r in NULLABLE_REASONS})
    for f in ("current_value", "as_of"):
        if nullable and record.get(f) is not None:
            raise ValueError(f"tripwire {f} must be NULL for status=UNKNOWN reason={reason}")
        if not nullable and record.get(f) is None:
            raise ValueError(f"tripwire {f} must be non-null for status={record['status']} reason={reason}")
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_tripwires.py -v`
Expected: 13 PASS.

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/output/tripwires.py demoflow/tests/test_tripwires.py
git commit -m "feat(demoflow): tripwire registry-bound source + UNKNOWN-branch nullability + value integrity + reason enum (§7c r2/r3/r6/r7/r8-F)"
```

### Task 29: Pipeline orchestrator + CLI (`demoflow run`, `demoflow tripwires`)

**Files:**
- Create: `demoflow/src/demoflow/output/artifacts.py`
- Create: `demoflow/src/demoflow/pipeline.py`
- Create: `demoflow/src/demoflow/cli.py`
- Test: `demoflow/tests/test_pipeline.py`

Rankings are a byproduct of `run` (single vintage, spec §7b). Wires the ROUNDS 7–9 contracts too:
the **identity envelope** {schema_version, data_vintage (incl source_hashes), assumptions_hash} above
the rows; the **projected-years-only** ranking domain (Statut=proj, contiguous through 2051); the
**central-value RUN CONTRACT** (q_live 0.085, φ 0.9/0.725, L=2, ratio center) + a per-geography
**rank_stable** robustness sweep; **P_resident ≥ 0** per cell before any consumer; the **general
no-open-string** tree-walk (source_hashes keys registry-bound, hashes 64-hex, timestamps ISO-8601).
All JSON `allow_nan=False` + finiteness asserted pre-write.

- [ ] **Step 1: Write the failing test**

`demoflow/tests/test_pipeline.py`:
```python
import json
import math

import pytest

from demoflow.pipeline import run_pipeline, HORIZON_YEARS
from demoflow.output.tripwires import REQUIRED_INDICATORS


def test_run_pipeline_emits_two_json_artifacts_with_identity_envelope(tmp_path):
    run_pipeline(out_dir=tmp_path, now_year=2026)
    ranks = json.loads((tmp_path / "rankings.json").read_text())
    assert ranks["schema"] == "demoflow.rankings.v1"
    assert "schema_version" in ranks and "assumptions_hash" in ranks        # identity envelope (r7-F6)
    assert "source_hashes" in ranks["data_vintage"]                         # codex r3-F6
    r0 = ranks["rankings"][0]
    assert isinstance(r0["geography"], str) and r0["rank"] == 1
    assert set(r0) == {"geography", "mean_ed_reference", "mean_ed_low", "mean_ed_high",
                       "rank", "rank_stable", "flags"}
    assert isinstance(r0["rank_stable"], bool)                              # typed sweep verdict

    trip = json.loads((tmp_path / "tripwire_baseline.json").read_text())
    assert trip["schema"] == "demoflow.tripwire_baseline.v1"
    assert trip["assumptions_hash"] == ranks["assumptions_hash"]            # same identity envelope
    inds = {t["indicator"] for t in trip["indicators"]}
    assert REQUIRED_INDICATORS <= inds
    for t in trip["indicators"]:
        assert {"indicator", "current_value", "source", "as_of", "band_low", "band_high", "status"} <= set(t)


def test_horizons_are_the_declared_set():
    assert HORIZON_YEARS == [2030, 2035, 2040, 2045, 2050]


def test_artifacts_reject_nan(tmp_path):
    from demoflow.output.artifacts import write_json_strict
    with pytest.raises(ValueError):
        write_json_strict(tmp_path / "x.json", {"schema": "t", "v": math.nan})


def test_no_open_string_rejects_smuggled_source_hashes_key():
    from demoflow.output.artifacts import assert_no_open_strings
    doc = {"data_vintage": {"source_hashes": {
        "crash_probability=0.35": {"sha256": "0" * 64, "extracted_at": "2026-07-21"}}}}
    with pytest.raises(ValueError, match="source_hashes key"):
        assert_no_open_strings(doc, frozenset({"ownership_by_geo_age.json"}))


def test_two_vintage_mixing_refused():
    from demoflow.output.rankings import refuse_cross_vintage
    from demoflow.errors import CalibrationError
    with pytest.raises(CalibrationError):
        refuse_cross_vintage({"hashA", "hashB"})     # identity envelope drives the refusal


def test_hors_rmr_fallback_iii_excluded_from_rankings_with_typed_record():
    # codex r10: unresolvable demand input -> EXCLUDED from rankings entirely (no ED row), named
    # in a typed run-level exclusion record; `unresolved_input` is a CLOSED enum (no free text).
    from demoflow.output.artifacts import rankings_document
    doc = rankings_document([], {"source_hashes": {}}, "h", frozenset(),
                            exclusions=[{"geography": "HORS_RMR", "unresolved_input": "immigrant_component_flows"}])
    assert doc["rankings"] == [] and doc["exclusions"][0]["geography"] == "HORS_RMR"
    with pytest.raises(ValueError, match="closed schema"):
        rankings_document([], {"source_hashes": {}}, "h", frozenset(),
                          exclusions=[{"geography": "HORS_RMR", "unresolved_input": "crash_probability=0.35"}])
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd demoflow && uv run pytest tests/test_pipeline.py -v`
Expected: FAIL (`ModuleNotFoundError: demoflow.pipeline`).

- [ ] **Step 3: Write the implementations**

`demoflow/src/demoflow/output/artifacts.py`:
```python
"""Golden-artifact JSON writers (spec §4/§7/§9). Identity envelope {schema_version,
data_vintage (incl source_hashes), assumptions_hash} above the rows; allow_nan=False +
finite pre-write; row allowlists + a general no-open-string tree-walk (codex r7-F6/r9-F3)."""
import json
import math
import re
from pathlib import Path

from demoflow.output.rankings import GeoRanking, assert_rankings_row_valid, ranking_row
from demoflow.output.tripwires import TripwireResult, assert_tripwire_record_valid, tripwire_record

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ].*)?$")


def _assert_finite(obj) -> None:
    if isinstance(obj, float) and not math.isfinite(obj):
        raise ValueError(f"non-finite value in artifact: {obj}")
    if isinstance(obj, dict):
        for v in obj.values():
            _assert_finite(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _assert_finite(v)


def assert_no_open_strings(doc: dict, allowed_source_keys: frozenset) -> None:
    """Every string position is registry/enum-bound or format-validated (codex r9-F3). Closes the
    source_hashes-KEY side-channel; validates sha256 (64-hex) + extracted_at (ISO-8601). Row-level
    enum/allowlist binding is enforced by assert_rankings_row_valid / assert_tripwire_record_valid."""
    sh = doc.get("data_vintage", {}).get("source_hashes", {})
    for key, val in sh.items():
        if key not in allowed_source_keys:
            raise ValueError(f"source_hashes key {key!r} not in the code-owned source registry")
        if not _HEX64.match(str(val.get("sha256", ""))):
            raise ValueError(f"source_hashes[{key}].sha256 is not 64-hex")
        if not _ISO_DATE.match(str(val.get("extracted_at", ""))):
            raise ValueError(f"source_hashes[{key}].extracted_at is not ISO-8601")


def write_json_strict(path: Path, obj: dict) -> None:
    _assert_finite(obj)                       # finite pre-write (codex r4-F3)
    with open(path, "w") as fh:
        json.dump(obj, fh, allow_nan=False, indent=2, sort_keys=True)
        fh.write("\n")


def _envelope(schema: str, vintage: dict, assumptions_hash: str) -> dict:
    return {"schema": schema, "schema_version": "1", "data_vintage": vintage,
            "assumptions_hash": assumptions_hash}


# Run-level exclusion (codex r10): a geography whose demand-side input is unresolvable (HORS_RMR
# fallback iii) is EXCLUDED FROM RANKINGS ENTIRELY — no ED row — and named in a typed exclusion
# record. `unresolved_input` is a CLOSED enum, never free text.
_UNRESOLVED_INPUTS = frozenset({"immigrant_component_flows"})


def rankings_document(rankings, vintage, assumptions_hash, allowed_source_keys, exclusions=()) -> dict:
    rows = [ranking_row(r) for r in rankings]
    for row in rows:
        assert_rankings_row_valid(row)        # closed allowlist + flags enum + typed rank_stable
    for exc in exclusions:
        if set(exc) != {"geography", "unresolved_input"} or exc["unresolved_input"] not in _UNRESOLVED_INPUTS:
            raise ValueError(f"exclusion record not in the closed schema {{geography, unresolved_input∈"
                             f"{sorted(_UNRESOLVED_INPUTS)}}}: {exc}")
    doc = {**_envelope("demoflow.rankings.v1", vintage, assumptions_hash),
           "rankings": rows, "exclusions": list(exclusions)}
    assert_no_open_strings(doc, allowed_source_keys)
    return doc


def tripwire_document(results, vintage, assumptions_hash, allowed_source_keys) -> dict:
    recs = [tripwire_record(t) for t in results]
    for rec in recs:
        assert_tripwire_record_valid(rec)     # closed allowlist + reason enum + registry-bound source
    doc = {**_envelope("demoflow.tripwire_baseline.v1", vintage, assumptions_hash), "indicators": recs}
    assert_no_open_strings(doc, allowed_source_keys)
    return doc
```

`demoflow/src/demoflow/pipeline.py`:
```python
"""Tranche-1 pipeline (spec §5/§6/§7, rounds 7–9). OwnerStock via the §7 defining equation;
native formation on P_resident (I2 operand binding + P_resident≥0); dimensional immigrant chain;
RUN-CONTRACT central values + rank_stable sweep; projected-years-only ranking domain; identity
envelope + source_hashes. COARSE by design (T1). YSL / beta mapping are Tranche 2."""
import hashlib
from pathlib import Path

import pandas as pd

from demoflow.balance.excess_demand import excess_demand
from demoflow.balance.owner_stock import owner_stock
from demoflow.cohort.basis import q_at
from demoflow.cohort.init import initialize_households
from demoflow.cohort.listings import ESTATE_LAG_YEARS, market_listings
from demoflow.cohort.rollforward import Stock, roll_one_year
from demoflow.demand.formation import immigrant_formation, native_formation, total_owner_demand
from demoflow.demand.i2 import assert_i2_identity, assert_p_resident_nonneg, p_resident
from demoflow.demand.immigrant_inputs import resolve_immigrant_inputs
from demoflow.geography import Geography, RA_PROXY_MEMBERS, Scenario
from demoflow.loaders.census import (
    headship_rate, load_headship_rates, load_ownership_rates, ownership_rate,
)
from demoflow.loaders.compo import load_immigrant_flows
from demoflow.loaders.constants import CENTRAL_ASSUMPTIONS, CONSTANTS, SWEEP_GRID, assumptions_hash
from demoflow.loaders.ircc import load_pr_landings
from demoflow.loaders.isq import load_population
from demoflow.loaders.living_arrangement import couple_share, living_alone_rate, load_living_arrangement
from demoflow.loaders.pins import DATA_DIR
from demoflow.output.artifacts import rankings_document, tripwire_document, write_json_strict
from demoflow.output.rankings import rank_geographies, refuse_cross_vintage
from demoflow.output.tripwires import (
    SourceKind, TripwireSpec, check_registry, evaluate_indicator, exit_code,
)

HORIZON_YEARS = [2030, 2035, 2040, 2045, 2050]   # ScenarioPrior horizons (T2 reference), NOT the ranking domain
_POP_WORKBOOKS = ["pop-as-rmr-base.xlsx", "pop-as-ra-base.xlsx"]
_COMPO_WORKBOOKS = ["compo-rmr-base.xlsx", "compo-ra-base.xlsx"]
ALLOWED_SOURCE_KEYS = frozenset(["ownership_by_geo_age.json", "headship_by_age.json", "living_arrangement.json"])
# codex r10: geographies whose demand-side inputs are unresolvable (HORS_RMR fallback iii) are
# EXCLUDED FROM RANKINGS ENTIRELY (no ED). Populated at probe P5/P6; EMPTY in the committed run
# (HORS_RMR's immigrant flows resolve from the compo hors-RMR row / province residual).
EXCLUDED_FROM_RANKINGS: frozenset = frozenset()


def _load_all(data_dir: Path | None):
    pop = pd.concat([load_population(w, data_dir=data_dir) for w in _POP_WORKBOOKS], ignore_index=True)
    compo = pd.concat([load_immigrant_flows(w, data_dir=data_dir) for w in _COMPO_WORKBOOKS], ignore_index=True)
    return pop, compo, load_ownership_rates(data_dir=data_dir), \
        load_headship_rates(data_dir=data_dir), load_living_arrangement(data_dir=data_dir)


def _projected_years(pop_g_s: pd.DataFrame) -> list[int]:
    """Ranking temporal domain (codex r8-F3): projected years only (Statut=proj), the full
    contiguous annual lattice through the last projected year (2051), both endpoints included."""
    proj = pop_g_s[pop_g_s["status"].astype(str).str.lower().str.startswith("proj")]
    return sorted(int(y) for y in proj["year"].unique())


def _pop_by_age(pop_g_s, year): return {int(a): float(v) for a, v in
                                        pop_g_s[pop_g_s["year"] == year].groupby("age")["population"].sum().items()}
def _ownership_by_age(ownership, geo): return {a: ownership_rate(ownership, geo, a) for a in range(25, 101)}
def _headship_by_age(headship): return {a: headship_rate(headship, a) for a in range(0, 101)}


def _init_stock(pop_g_s, year, ownership, la, geo) -> Stock:
    r = pop_g_s[(pop_g_s["year"] == year) & (pop_g_s["age"] >= 75)]
    pop_by_sex = {s: float(r[r["sex"] == s]["population"].sum()) for s in ("M", "F")}
    h = initialize_households(
        pop_by_sex,
        living_alone_rate_by_sex={s: living_alone_rate(la, geo, 80, s) for s in ("M", "F")},
        couple_share_by_sex={s: couple_share(la, geo, 80, s) for s in ("M", "F")},
        collective_share=CONSTANTS["collective_share_75plus"].value,
        ownership_rate=ownership_rate(ownership, geo, 80),
    )
    return Stock(couple=h.owner_couple, solo_m=h.owner_solo_m, solo_f=h.owner_solo_f)


def _ed_series(geo, scen, pop, compo, ownership, headship, la, q_live) -> list[float]:
    """ED at every PROJECTED year (the ranking domain). q_live is passed so the rank_stable
    sweep can re-run at the band endpoints; the headline run uses the central value."""
    inp = resolve_immigrant_inputs(geo)
    p_nonimm = ownership_rate(ownership, geo, 40)
    hs, own = _headship_by_age(headship), _ownership_by_age(ownership, geo)
    pop_g_s = pop[(pop["geography"] == geo) & (pop["scenario"] == scen)]
    compo_g_s = compo[(compo["geography"] == geo) & (compo["scenario"] == scen)]
    years = _projected_years(pop_g_s)
    base_year = int(pop_g_s["year"].min())

    stock = _init_stock(pop_g_s, base_year, ownership, la, geo)
    estate, voluntary = {}, {}
    for year in range(base_year, years[-1] + 1):
        nxt, exits = roll_one_year(stock, age=80, year=year, q_live=q_live, qx=q_at)
        entrants = _init_stock(pop_g_s, min(year + 1, int(pop_g_s["year"].max())), ownership, la, geo)
        inflow = max(entrants.owner_units - stock.owner_units, 0.0) * 0.1
        stock = Stock(nxt.couple + inflow, nxt.solo_m, nxt.solo_f)
        estate[year], voluntary[year] = exits["estate"], exits["living"]
    listings = market_listings(voluntary, estate, lag=ESTATE_LAG_YEARS)

    def _scale(year):
        p_isq = float(pop_g_s[pop_g_s["year"] == year]["population"].sum())
        surviving = [float(compo_g_s[compo_g_s["year"] == y]["immigrants_permanents"].sum())
                     for y in range(base_year, year + 1)]
        p_res = assert_p_resident_nonneg(p_resident(p_isq, surviving), ctx=f"{geo.value}/{scen.value}/{year}")
        return (p_res / p_isq if p_isq > 0 else 1.0), p_isq, surviving

    series = []
    for t in years:
        scale_t, p_isq_t, surviving_t = _scale(t)
        scale_tm1, _, _ = _scale(t - 1)
        resident_t = {a: p * scale_t for a, p in _pop_by_age(pop_g_s, t).items()}
        resident_tm1 = {a: p * scale_tm1 for a, p in _pop_by_age(pop_g_s, t - 1).items()}
        assert_i2_identity(sum(resident_t.values()), p_isq_t, surviving_t)   # operand binding
        D = total_owner_demand(
            native_formation(resident_t, resident_tm1, hs, own),
            immigrant_formation(float(compo_g_s[compo_g_s["year"] == t]["immigrants_permanents"].sum()),
                                inp.immigrant_headship, p_nonimm, inp.ownership_ratio))
        os = owner_stock(_pop_by_age(pop_g_s, t), hs, own)   # §7 defining equation
        series.append(excess_demand(D, listings.get(t, 0.0), os))
    return series


def _ed_dict(geos, pop, compo, ownership, headship, la, q_live):
    return {g: {sc: _ed_series(g, sc, pop, compo, ownership, headship, la, q_live)
                for sc in (Scenario.REFERENCE, Scenario.LOW, Scenario.HIGH)} for g in geos}


def _rank_stability(geos, pop, compo, ownership, headship, la) -> dict:
    """RUN-CONTRACT robustness sweep (codex r8-F1): a geography's rank is STABLE iff it is
    unchanged at both q_live band endpoints vs the central value."""
    lo, hi = SWEEP_GRID["q_live_per_year"]
    orders = [ {r.geography: r.rank for r in rank_geographies(_ed_dict(geos, pop, compo, ownership, headship, la, q))}
               for q in (CENTRAL_ASSUMPTIONS["q_live_per_year"], lo, hi) ]
    return {g: all(o[g] == orders[0][g] for o in orders) for g in geos}


def _source_hashes(data_dir: Path | None) -> dict:
    dd = data_dir or DATA_DIR
    return {name: {"sha256": hashlib.sha256((dd / name).read_bytes()).hexdigest(),
                   "extracted_at": "2026-07-21"}
            for name in ALLOWED_SOURCE_KEYS if (dd / name).exists()}


def _vintage(data_dir: Path | None) -> dict:
    return {"isq_edition": "mise a jour 2026", "census_year": 2021, "constants_as_of": "2026",
            "source_hashes": _source_hashes(data_dir)}


def _tripwire_results(now_year: int) -> list:
    pr = load_pr_landings()
    specs = [
        (TripwireSpec("pr_landings_annual", 40000.0, 50000.0, 2026, 1, SourceKind.WIRED),
         (45000.0 if pr.available else None), pr.available),
        (TripwireSpec("temp_resident_stock", 0.0, 1e9, 2026, 1, SourceKind.WIRED), None, False),
        (TripwireSpec("isq_edition_watch", 2025.5, 2027.5, 2026, 1, SourceKind.WIRED), 2026.0, True),
        (TripwireSpec("registre_foncier_volume", 0.0, 1e9, 2026, 1, SourceKind.OPERATOR_SUPPLIED), None, True),
        (TripwireSpec("cmhc_senior_sale_5yr", 0.30, 0.42, 2021, 5, SourceKind.OPERATOR_SUPPLIED),
         CONSTANTS["cmhc_senior_sale_5yr"].value, True),
        (TripwireSpec("natural_increase_sign", -1e9, 1e9, 2026, 1, SourceKind.OPERATOR_SUPPLIED), -1200.0, True),
    ]
    results = [evaluate_indicator(s, v, available=a, now=now_year) for s, v, a in specs]
    results += check_registry([s.indicator for s, _, _ in specs])   # completeness (empty here)
    return results


def run_pipeline(data_dir: Path | None = None, out_dir: Path | None = None, now_year: int = 2026):
    pop, compo, ownership, headship, la = _load_all(data_dir)
    ah = assumptions_hash()
    refuse_cross_vintage({ah})   # identity envelope drives the same-vintage refusal

    present = [g for g in Geography if g in set(pop["geography"].unique())]
    geos = [g for g in present if g not in EXCLUDED_FROM_RANKINGS]   # excluded geos carry NO ED
    exclusions = [{"geography": g.value, "unresolved_input": "immigrant_component_flows"}
                  for g in present if g in EXCLUDED_FROM_RANKINGS]
    ed = _ed_dict(geos, pop, compo, ownership, headship, la, CENTRAL_ASSUMPTIONS["q_live_per_year"])
    borrowed = {g for g in geos if g in RA_PROXY_MEMBERS or g is Geography.HORS_RMR}
    stable = _rank_stability(geos, pop, compo, ownership, headship, la)
    rankings = rank_geographies(ed, borrowed=borrowed, rank_stable=stable)

    trips = _tripwire_results(now_year)
    vintage = _vintage(data_dir)
    out_dir = Path(out_dir) if out_dir else Path.cwd() / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json_strict(out_dir / "rankings.json",
                      rankings_document(rankings, vintage, ah, ALLOWED_SOURCE_KEYS, exclusions=exclusions))
    write_json_strict(out_dir / "tripwire_baseline.json", tripwire_document(trips, vintage, ah, ALLOWED_SOURCE_KEYS))
    return {"rankings": rankings, "tripwires": trips, "exit_code": exit_code(trips), "out_dir": out_dir}
```

`demoflow/src/demoflow/cli.py`:
```python
"""demoflow CLI (spec §3): `demoflow run` emits rankings + tripwire artifacts;
`demoflow tripwires` re-evaluates tripwires and sets the exit code (0 iff all OK)."""
import argparse
import sys
from pathlib import Path

from demoflow.pipeline import run_pipeline
from demoflow.output.tripwires import exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="demoflow")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, help_ in [("run", "emit rankings + tripwire artifacts"), ("tripwires", "evaluate tripwires")]:
        p = sub.add_parser(name, help=help_)
        p.add_argument("--out", type=Path, default=Path("artifacts"))
    args = parser.parse_args(argv)

    result = run_pipeline(out_dir=args.out)
    if args.cmd == "run":
        print(f"wrote {args.out}/rankings.json and {args.out}/tripwire_baseline.json")
        return 0
    for t in result["tripwires"]:
        reason = f" — {t.reason.value}" if t.reason else ""
        print(f"{t.status.value:8} {t.indicator} ({t.source}){reason}")   # t.source is the declared string
    return exit_code(result["tripwires"])


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_pipeline.py -v`
Expected: 6 PASS. (Coarse-model cautions: the rank_stable sweep runs the ED grid three times — if an
ED denominator drops below the 1,000-household guard, or the couple balance gate raises on the
committed per-sex rates, calibrate `living_arrangement.json` per-geo from P3 so `coupled_m ≈
coupled_f`; the golden pins whatever the calibrated vintage produces — no exact ED numbers asserted.)

- [ ] **Step 5: Commit**

```bash
git add demoflow/src/demoflow/output/artifacts.py demoflow/src/demoflow/pipeline.py demoflow/src/demoflow/cli.py demoflow/tests/test_pipeline.py
git commit -m "feat(demoflow): pipeline identity envelope + projected-year domain + rank_stable sweep + P_resident>=0 + no-open-string (§7/§9 r7/r8/r9-F)"
```

---

### Task 30: Golden artifacts (committed rankings + tripwire baseline; generate → commit → diff)

**Files:**
- Create (by running): `demoflow/artifacts/rankings.json`, `demoflow/artifacts/tripwire_baseline.json`
- Test: `demoflow/tests/test_golden.py`

Golden = generate from the committed data vintage, COMMIT the output, then a regression
test re-runs and diffs. No exact numbers are pre-known here (they follow from the committed
vintage); the golden is the pin.

- [ ] **Step 1: Generate + commit the golden artifacts**

Run:
```bash
cd demoflow && uv run demoflow run --out artifacts
cat demoflow/artifacts/rankings.json | head -30
```
Expected: writes `demoflow/artifacts/rankings.json` + `demoflow/artifacts/tripwire_baseline.json`,
JSON with `allow_nan=False`, sorted keys. Inspect that ranks are contiguous from 1, geographies
are string values, and `flags` carries `ra_proxy` on the RA members.

- [ ] **Step 2: Write the regression (golden-diff) test**

`demoflow/tests/test_golden.py`:
```python
import json
from pathlib import Path

from demoflow.pipeline import run_pipeline

GOLDEN = Path(__file__).resolve().parent.parent / "artifacts"

# THIRD, TEST-OWNED copy of the code-required indicator name list (codex r4-F4): a
# co-deletion must touch code (REQUIRED_INDICATORS) + baseline (golden) + this test in ONE
# PR-visible diff — the residual guard no runtime check can provide.
_REQUIRED_INDICATOR_NAMES = {
    "pr_landings_annual", "temp_resident_stock", "isq_edition_watch",
    "registre_foncier_volume", "cmhc_senior_sale_5yr", "natural_increase_sign",
}


def test_rankings_match_golden(tmp_path):
    run_pipeline(out_dir=tmp_path, now_year=2026)
    fresh = json.loads((tmp_path / "rankings.json").read_text())
    committed = json.loads((GOLDEN / "rankings.json").read_text())
    assert fresh == committed


def test_tripwire_baseline_matches_golden(tmp_path):
    run_pipeline(out_dir=tmp_path, now_year=2026)
    fresh = json.loads((tmp_path / "tripwire_baseline.json").read_text())
    committed = json.loads((GOLDEN / "tripwire_baseline.json").read_text())
    assert fresh == committed
    inds = {t["indicator"] for t in committed["indicators"]}
    assert _REQUIRED_INDICATOR_NAMES <= inds       # literal name list pinned here (third copy)


def test_golden_is_strict_json_no_nan():
    for name in ("rankings.json", "tripwire_baseline.json"):
        text = (GOLDEN / name).read_text()
        assert "NaN" not in text and "Infinity" not in text
```

- [ ] **Step 3: Run to verify it passes**

Run: `cd demoflow && uv run pytest tests/test_golden.py -v`
Expected: 3 PASS (fresh run reproduces the committed golden deterministically).

- [ ] **Step 4: Commit**

```bash
git add demoflow/artifacts/rankings.json demoflow/artifacts/tripwire_baseline.json demoflow/tests/test_golden.py
git commit -m "test(demoflow): committed golden rankings + tripwire baseline (generate->commit->diff)"
```

**End of T1c session boundary.**

### Task 31: Quant-financial-engineer audit (pre-PR gate)

**Goal:** Adversarial methodology audit of every formula, unit conversion, and arithmetic claim in
this plan, against the implemented code.

**Files:**
- Read: `docs/plans/2026-07-21-demoflow-tranche1.md`
- Read: `docs/specs/2026-07-21-demoflow-demographic-scenario-module-design.md`
- Write: `docs/audits/quant/2026-07-21-demoflow-tranche1.md`

- [ ] **Step 1: Dispatch agent.** Use the `Agent` tool with
  a quant / financial-engineering review agent. Hand it the plan path, the spec path, and this framing:
  > "For every formula, unit, and arithmetic claim in this plan: run dimensional-consistency +
  > limiting-cases on the plan's specifics — the q_live annualization 1−(1−0.36)^(1/5); the
  > competing-risk partition (branches sum to 1, all ≥0, incl. couple states); the persons→households
  > conversions (person- vs household-denominated rates, the min-matching + excess routing); the
  > I2 decomposition (P_resident ≥ 0, surviving-cohort survival arithmetic); the ED equation's units
  > (households/households, annual); the ranking collapse determinism (ties, crossings, temporal
  > domain); the CPM basis usage (year-projection, sex mapping, 100+ absorbing bucket). Junction-type
  > trace on every cross-source join (geography labels, sex codes, age blocks). Verify the ORACLE
  > fixtures' hand-computed values by independent recomputation — a wrong oracle pins a wrong
  > implementation. Verdict: PROCEED / PROCEED-WITH-MODIFICATIONS / REPLACE-REDESIGN. Flag which
  > findings are decision-critical (wrong-number vectors for the operator's own outputs) vs
  > nice-to-have."
- [ ] **Step 2: Read the verdict.** For each DECISION-CRITICAL finding, FOLD it into a task or
  REVISE the offending task. After any fold, re-grep the WHOLE plan for terms the fold superseded.
- [ ] **Step 3: Primary-source verify** any load-bearing factual claim in the verdict before acting.
- [ ] **Step 4: Commit the verdict** to `docs/audits/quant/2026-07-21-demoflow-tranche1.md`.
- [ ] **Step 5: If DECISION-CRITICAL folds happened, re-dispatch** the agent on the revised plan once.

### Task 32: Stress-tester audit (pre-PR gate)

**Goal:** Adversarially probe every load-bearing claim in this plan AND inspect the newly-written
guard/validation code.

**Files:**
- Read: `docs/plans/2026-07-21-demoflow-tranche1.md`
- Read: `git diff <branch-base>..HEAD` for the implemented demoflow code
- Write: `docs/audits/stress/2026-07-21-demoflow-tranche1.md`

- [ ] **Step 1: Dispatch agent.** Use `Agent` with `subagent_type: stress-tester`. Hand it the plan
  path, the SHA range, and this framing:
  > "Adversarially probe every load-bearing claim in this plan: 'fail-loud, never impute',
  > 'never a false clean' (tripwires), 'no open string anywhere' (the tree-walk validator),
  > 'schema cannot express the forbidden quantities', 'mechanically unshippable double-count'.
  > Run predicate-vs-claim + guard-mutation on EVERY guard the plan adds (mutate the guard to a
  > no-op AND delete the subject it protects AND delete the call site — a body-tested guard can
  > still be unpinned at its wiring); cheapest-passing-world on every done-bar (especially the
  > golden-artifact diffs and the reconciliation envelope); test-double-vs-production divergence on
  > the committed-workbook fixtures vs pinned re-download path; degenerate ledger with
  > cause-owner + error-direction on every loader; composition across the shared assumptions_hash
  > (can two artifacts mix identities?). Probe against the real committed workbooks, not synthetic
  > fixtures, wherever claims are empirical. Report each finding with a concrete executable probe."
- [ ] **Step 2: Read the report.** Every CRITICAL → fold into a task or REVISE.
- [ ] **Step 3: Run a regression** confirming each fold closes its probe; mutation-test every guard
  a fold ADDS before committing it.
- [ ] **Step 4: Commit the report** to `docs/audits/stress/2026-07-21-demoflow-tranche1.md`.
- [ ] **Step 5: If CRITICAL folds happened, re-dispatch** on the revised hardening.

### Task 33: Data-integrity-validator audit (pre-PR gate)

**Goal:** Adversarial attack on the data layer for junction defects, vintage/PIT identity holes,
and staleness blind spots.

**Files:**
- Read: `docs/plans/2026-07-21-demoflow-tranche1.md`
- Read: every loader module + `demoflow/data/` + the probe observation notes
- Write: `docs/audits/data/2026-07-21-demoflow-tranche1.md`

- [ ] **Step 1: Dispatch agent.** Use the `Agent` tool with
  a data-integrity review agent. Hand it the plan path, the loader file paths,
  and this framing:
  > "Attack the data layer: junction-type trace on every cross-source join (geography label
  > normalization incl. trailing-space/footnote-digit reality, sex-code orientation, age-block
  > selection under duplicate column names, scenario label mapping); vintage/PIT identity — can two
  > runs with different upstream bytes emit the same artifact identity (source_hashes coverage,
  > extracted_at semantics)? Staleness — silence-test the tripwire freshness gate: can it EVER
  > report UNKNOWN vacuously or stale-as-fresh? Year-lattice + primary-key contracts against the
  > REAL committed workbooks (probe the actual sheets — do the pinned expectations hold on the real
  > population, not one sampled row?). Consumer-blast-radius per defect. Verdict: PROCEED /
  > PROCEED-WITH-MODIFICATIONS / REDESIGN."
- [ ] **Step 2: Read the verdict.** Every CRITICAL finding → fold into a task or revise.
- [ ] **Step 3: Commit the verdict** to `docs/audits/data/2026-07-21-demoflow-tranche1.md`.
- [ ] **Step 4: If CRITICAL folds happened, re-dispatch** on the revised plan.

## Verification

- [ ] **Full suite green from `demoflow/`:**
  ```bash
  cd demoflow && uv run pytest -q
  ```
  Expected: all T1a + T1b + T1c tests pass. Then confirm the two live/entry-point paths:
  ```bash
  cd demoflow && uv run python -O -m pytest tests/test_basis_guard.py -q   # -O: guard survives assertion-stripping
  cd demoflow && uv run demoflow tripwires --out /tmp/demoflow_trip ; echo "exit=$?"  # exit 0 iff all OK, nonzero on CROSSED/UNKNOWN
  ```

- [ ] **§10 fixture inventory (every Tranche-1 anchor — incl. codex rounds 1–6 — has a running test):**

  | Spec §10 anchor | Task | Test |
  |---|---|---|
  | Oracle q_x cross-env (M75=0.0156, F75=0.0115) | 1 (P1) | `test_probe_p1.py::test_qc_basis_qx_matches_skeleton_oracle` |
  | Loader validation: fraction∈[0,1] / finite / PK / pinned+uniform year lattice | 8b | `test_validate.py` |
  | Geography TOTAL map: modeled→enum, unmodeled→IGNORED, outside-set→raise | 9 | `test_geography.py` |
  | Sex ORIENTATION guard RED (swapped 1↔2 → 85+ female-excess check raises) | 11 | `test_isq_loader.py::test_sex_orientation_guard_raises_on_swapped_map` |
  | couple_share is NOT a constant (blocker fix); cited-or-raise | 15,15b | `test_constants.py::test_couple_share_is_NOT_a_constant`, `test_living_arrangement.py::test_missing_couple_share_raises_no_invented_default` |
  | F1 three-bucket per-sex init: 100+100→60/0/0; general 200/0.25/0.80→50/60/30 | 18 | `test_init.py::test_all_coupled_100_100_60pct_ownership`, `::test_general_case_three_buckets_and_person_conservation` |
  | Couple matching: 100v80→80+20 Other; 20v100→CalibrationError; 0v0→0 | 18 | `test_init.py::test_match_couples_*` |
  | q_live annualization 1−(1−0.36)^(1/5) ≈ 8.5%, band [0.06,0.11] | 19 | `test_q_live.py` |
  | F3 competing-risk partition (0.20/0.08/0.72, sums to 1; widow retained) | 20 | `test_partition.py` |
  | RED: q outside [0,1] MUST raise | 20 | `test_partition.py::test_q_outside_unit_raises` |
  | Reconciliation gate [0.20,0.40] → CalibrationError | 21 | `test_reconciliation_gate.py` |
  | F2 double-decrement mutation is ORACLE-EXACT (pinned values change), envelope=gross backstop; band-entry once | 22 | `test_rollforward.py::test_double_decrement_mutation_changes_pinned_oracle` |
  | Reconciliation composition pinned (MTL_RMR mix); per-state paths (Solo_m/Solo_f/Couple) pinned | 21, 23 | `test_reconciliation_gate.py`, `test_cohort_oracle.py` |
  | 2-cohort/3-year oracle (widow timing) + 100+ absorbing bucket + mass conservation | 23 | `test_cohort_oracle.py` |
  | Transfer-vs-market split (φ_market + estate-lag convolution) | 24 | `test_listings.py` |
  | Dimensional headship (100 arrivals as 50 couples vs 100 singles → DIFFERENT D) | 25 | `test_demand.py::test_dimensional_headship_50_couples_vs_100_singles_differ` |
  | Native formation disjoint from S (75+ decline invisible to D); p_imm∈[0,1] | 25 | `test_demand.py::test_native_ignores_75plus_changes_disjoint_from_S`, `::test_p_imm_is_product_asserted_in_unit_interval` |
  | I2 decomposition + double-entry mutation (feeding total ISQ → gate fails) | 25b | `test_i2.py::test_i2_identity_gate_passes_on_consistent_and_fails_on_mutation` |
  | Immigrant-input join (direct / parent-CMA / province / unresolved→raise) | 25b | `test_i2.py::test_join_direct_borrowed_and_raise` |
  | OwnerStock defining equation (all-age, PIT-fixed) | 26 | `test_owner_stock.py` |
  | F4 hand-worked ED (estate-lag crossing); OwnerStock<1000 numeric guard (999/1000/1001) | 26 | `test_excess_demand.py` |
  | Native a_min=18 forms against zero prior (no negative-index wraparound) | 25 | `test_demand.py::test_native_at_a_min_18_forms_against_zero_prior_no_wraparound` |
  | Immigrant ratio nonneg-finite carve-out (>1 valid); P_resident≥0 per cell | 8b, 25b | `test_validate.py::test_nonneg_finite_ratio_carveout_allows_gt_one`, `test_i2.py::test_p_resident_nonnegativity_per_cell` |
  | Signed-flow carve-out (natural-increase tripwire evaluates a negative value) | 8b, 29 | `test_validate.py` (note) + pipeline `natural_increase_sign` = −1200 |
  | Run-contract central values (q_live 0.085, φ 0.9/0.725, L=2) + assumptions_hash | 15, 24 | `test_constants.py::test_central_assumptions_and_hash`, `test_listings.py::test_phi_central_values` |
  | rank_stable typed bool (robustness sweep); ordering reverses all-years vs projected-only | 27 | `test_rankings.py::test_rank_stable_is_typed_bool_not_a_flag_string`, `::test_ordering_reverses_all_years_vs_projected_only` |
  | Tripwire source bound to registry; UNKNOWN-branch nullability (non_finite → null) | 28 | `test_tripwires.py::test_source_bound_to_code_owned_registry`, `::test_unknown_branch_nullability_contract` |
  | Identity envelope on both files; two-vintage mixing refused; no-open-string (source_hashes key) RED | 29 | `test_pipeline.py::test_run_pipeline_emits_two_json_artifacts_with_identity_envelope`, `::test_two_vintage_mixing_refused`, `::test_no_open_string_rejects_smuggled_source_hashes_key` |
  | F4 ranking (unique ordering, exact tie); scenario-NAMED fan crossing | 27 | `test_rankings.py::test_unique_ordering_with_exact_tie`, `::test_scenario_named_fan_fields_can_cross` |
  | Rankings row allowlist + closed flags enum + crash_probability RED (field+flag) | 27 | `test_rankings.py::test_row_allowlist_exact_and_flag_enum_reject_crash_probability` |
  | Ranking same-vintage refusal | 27 | `test_rankings.py::test_cross_vintage_comparison_refused` |
  | Tripwire fail-safe + value integrity (stale/unavailable/missing/non-finite/future-as_of/inverted-band → UNKNOWN; closed bands → CROSSED) | 28 | `test_tripwires.py` (RED false-clean cases) |
  | Tripwire code-owned registry completeness (empty/missing/duplicate → nonzero) | 28 | `test_tripwires.py::test_registry_completeness_empty_missing_duplicate` |
  | Tripwire record allowlist + closed reason enum + crash_probability RED (field+reason) | 28 | `test_tripwires.py::test_record_allowlist_and_reason_enum_reject_crash_probability` |
  | Required-indicator name list pinned LITERALLY in test (third copy) | 30 | `test_golden.py::test_tripwire_baseline_matches_golden` |
  | Loader sha256 pins + drift raise | 8 | `test_pins.py` |
  | Loader schema-drift raises (age-block group, header tokens, additivity) | 10,11,12 | `test_isq_ages.py`, `test_isq_loader.py`, `test_compo_loader.py` |
  | Import-direction contract (demoflow ⊥ hde both ways; mcp_server = actuarial's) | 16 | `test_import_direction.py` |
  | Basis guard F7 (normal path; guard raises + get_qx never called; survives −O) | 17 | `test_basis_guard.py` |
  | Golden artifacts (allow_nan=False + finite pre-write + source_hashes) | 29,30 | `test_pipeline.py`, `test_golden.py` |

- [ ] **Probes recorded + committed:** `demoflow/probes/P1..P6` observation notes exist; each states a VERDICT or a recorded failure + the spec-named fallback (never a silent proceed).

- [ ] **Adversarial audits — pre-PR (Tasks 31–33) AND PR-time.** The three injected pre-PR audits (Task 31 quant-financial-engineer, Task 32 stress-tester, Task 33 data-integrity-validator) run after T1c and BEFORE the PR — their findings fold into the branch. At PR time `stress-tester` fires AGAIN via the external review hook (alongside codex + DeepSeek). Then land the branch.

## Out of scope (Tranche 2 — gated, do NOT build here)

Tranche 2 is DEFERRED behind a named artifact: **a one-page S4b demographic-input-slot
sketch**, authored in S4b's own design session (which itself consumes merged S4a). S4b's
roadmapped contract currently has NO demographic slot — building the emitter against an
imagined consumer is the sequencing inversion the 2B gate caught (spec §1/§12). Deferral
costs nothing: the artifact is unconsumable until S4b exists.

**Explicitly NOT in this plan (Tranche 2):**
- **ScenarioPrior artifact emitter** (spec §7a) — JSON, one row per (geography × dwelling_type ×
  horizon ∈ {2030,2035,2040,2045,2050} × scenario), with `demo_drift_{mean,p10,p90}`,
  `drawdown_weight_tilt`, `excess_demand_fraction`, `flags[]` a CLOSED enum {borrowed_prior,
  ra_proxy, never_relax_stress}, and `data_vintage.source_hashes` (the T1 rankings/tripwire
  artifacts already carry source_hashes, Task 29). Enum → string at the boundary.
- **Schema-allowlist contract tests + the F6 RED integrity fixtures** (spec §7/§10): field-set
  allowlist (no `crash_probability`), `never_relax_stress` present on every `drawdown_weight_tilt < 1.0`
  row, complete Cartesian product / no duplicate keys, `allow_nan=False`, band ordering
  `p10 ≤ mean ≤ p90`, `drawdown_weight_tilt ≥ 0`, enum-domain membership — one RED fixture each
  (missing row, duplicate key, NaN, inverted band, negative tilt, unknown enum).
- **ED→drift mapping** (`balance/mapping.py`, spec §7 r3-F7/r6-F5): v0 form is LINEAR THROUGH THE
  ORIGIN `demo_drift = β × ED` (decimal real drift/yr; worked fixture ED=0.01, β=2.0 → 0.02 = 2%/yr).
  β is UNIFORM over [1.0, 4.0], so drift quantiles are CLOSED-FORM: mean = 2.5 × ED; for ED ≥ 0,
  p10/p90 = β's 10th/90th quantile × ED (reversed for ED < 0). Zero intercept by construction; any
  knots/saturation or non-uniform β prior is a Tranche-2 decision made WITH the S4b sketch.
  `mapping_version` stamp + bump-enforcement test. β is unvalidatable until the consumer exists.
- **Immigrant YSL S-curve** (ROC-CHSP borrowing) + **QC-discount multiplier band [0.60, 0.85]**
  (`borrowed_prior`) + the **plex owner-occupier-landlord tilt** (spec §6).
- **`never_relax_stress` contract enforcement** (rides the emitter): the S4b integration spec must
  honor the flag semantics; demoflow flags, never clamps (flag-not-clamp is deliberate, spec §1).

**Input-slot sketch (the gate the operator/S4b session fills before Tranche 2 starts):**
S4b must declare, per its Monte-Carlo generator, (1) the demographic input SHAPE it consumes
(drift-band prior on its price-drift generator + a ≥0 tilt on its shock weights — raw inputs, S4b
self-derives shocks), (2) the geography × dwelling_type × horizon × scenario grid it indexes, and
(3) which artifact-identity fields (data_vintage, assumptions_hash, mapping_version, schema_version)
it records at consumption. Absent that sketch, Tranche 2 does not start.

**Named Tranche-2 contract DEBTS the S4b sketch inherits (codex r10 — currently unspecified, must be
pinned WITH the sketch, never improvised):**
1. **ED-trajectory → horizon-row aggregation rule.** Tranche 1 emits a full projected-year ED
   trajectory; the ScenarioPrior row is per horizon_year ∈ {2030,2035,2040,2045,2050}. HOW the
   trajectory collapses to a horizon value — the endpoint at that year vs a period-mean over the
   surrounding window — is undefined and determines every emitted drift number.
2. **ED → `drawdown_weight_tilt` mapping.** β (§7) maps ED → real price DRIFT only; the ≥0
   `drawdown_weight_tilt` on S4b's shock probability has NO defined relationship to ED yet. This
   mapping (and its `never_relax_stress` floor semantics) is a distinct Tranche-2 contract.

**v1+ / CUT / REJECTED (spec §13):** MRC couronne split (pending source); plex compute + rôle-CUBF
stock; StatCan paid CT-level tabulation; >2051 horizon tail; actuarial-system multiple-decrement
combinator (charter extension); tripwire scheduling/cron. CUT: parquet mirror, `weak_identification`
flag. REJECTED: forecaster-lite.

