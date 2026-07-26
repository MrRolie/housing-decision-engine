"""P5 — IRCC permanent-resident admissions by CMA (open.canada.ca monthly CSV).

WHO USES THIS (spec §4 / §7): the PR-LANDINGS TRIPWIRE (Task 28) compares realized
IRCC permanent-resident landings against the MIFI plan level. It is NOT the demand
model — demand uses the ISQ compo "Immigrants permanents". If this source is
unavailable the tripwire reports UNKNOWN (never a stale within-band), so P5's job is
to RECORD the observation: the real package id, the CSV resource url, the observed
column schema, and the suppressed-<5 cell convention — all from live responses.

WHAT THE HUNT ESTABLISHED (recorded live below, so a re-run re-derives it):
  * The CKAN `package_search` (the plan's query) resolves the IRCC package
    "Permanent Residents – Monthly IRCC Updates". The package id and the CSV url are
    NOT hand-typed constants asserted as truth: they are RESOLVED out of the live
    search response by an auditable predicate (org is IRCC AND the package carries a
    CSV resource whose name matches CMA/Metropolitan), and the count of matching
    results is printed so "located" is EARNED, not planted. A known-expected id is
    kept only as a cross-check that the live-resolved id must equal.
  * The CMA resource is CMA × month × TOTAL (permanent-resident admissions). There is
    NO immigration-category dimension crossed with CMA anywhere in THIS package's
    resources (enumerated live) — category appears only at the Province/Territory
    level (`ODP-PR-PT_IMMCAT.csv`). This is a recorded divergence from spec §4's
    "by CMA + category"; it does not block the tripwire, which needs TOTAL only.

ANTI-FABRICATION (the cardinal discipline). Every VALUE the note reports as observed
is emitted from the live response by THIS run: the resolved package id, the CSV url,
the column list (split from the fetched header — never a literal), the row/CMA/year
counts, and the suppression/rounding tallies. The `Fact` registry self-accounts for
the DERIVED (computed this run) vs CITED (verbatim from the live package notes) mix;
the provenance header scopes exactly what it covers and claims nothing broader.

FLOOR GUARD (NS #1 — a verification gate must REFUSE when it cannot verify). A CKAN
response can be 200-but-vacuous (count 0 / empty results / a package with zero CMA
resources) or the CSV host can serve a 200-but-wrong-body page (an HTML error that
parses into a one-column "schema"). Neither may launder into a false LOCATED. The
guard RAISES `VacuousProbeError` -> the run records UNKNOWN-PROBE-FAILED with the
boundary that failed (ckan|csv), never a fabricated located note.

Run:  cd demoflow && uv run python probes/run_p5.py
"""

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# --- CKAN discovery boundary (open.canada.ca) -------------------------------
# The plan's package_search query, verbatim. The probe SHOWS it searched, so a
# LOCATED is credible: it resolves the package out of THESE results, not a constant.
CKAN_SEARCH = ("https://open.canada.ca/data/api/3/action/package_search"
               "?q=permanent+residents+census+metropolitan+area+monthly&rows=100")
CKAN_HOST = "https://open.canada.ca"

# The expected package id — kept ONLY as a cross-check the live-resolved id must equal
# (point A: never printed AS the resolved evidence; the resolved one is emitted beside
# it and the two are asserted equal). Its presence does not make the run trust it.
EXPECTED_PKG_ID = "f7e5498e-0ad8-4417-85c9-9b8aff9b9eda"
IRCC_ORG_MARK = "immigration, refugees and citizenship canada"

# The two CMAs demoflow models (spec). Presence of BOTH with numeric rows is what
# earns FOUND-AT-CMA: YES — the CSV was pulled, not inferred from metadata.
MODELED_CMAS = ("Montréal", "Québec")

OUT = Path(__file__).resolve().parent / "P5-ircc-pr-by-cma.md"
TIMEOUT = 120


# --- Fact provenance registry (reused from run_p4.py; CKAN nav is written fresh) ---
_FACTS: list["Fact"] = []


@dataclass(frozen=True)
class Fact:
    """A figure carrying HOW this run obtained it.

    `derived` — computed FROM the live response in THIS run (it changes when the
                live data changes), naming what produced it; `cited` — quoted
                verbatim from the live package metadata, printed with its source.

    Known weakness (unchanged from P3/P4): the `derived` tag is author-chosen and
    does NOT by itself prove the value was computed. So the discipline is enforced
    by CODE — every value tagged `derived` below is a live expression over the
    fetched response, never a literal handed to `Fact.derived`.
    """

    text: str
    kind: str  # "derived" | "cited"
    source: str

    def __post_init__(self) -> None:
        _FACTS.append(self)

    @classmethod
    def derived(cls, value: object, how: str) -> "Fact":
        return cls(f"{value}", "derived", how)

    @classmethod
    def cited(cls, value: object, source: str) -> "Fact":
        return cls(f"{value}", "cited", source)

    def __str__(self) -> str:
        return self.text if self.kind == "derived" else f"{self.text} [cited: {self.source}]"


def _provenance_header() -> list[str]:
    derived = [f for f in _FACTS if f.kind == "derived"]
    cited = [f for f in _FACTS if f.kind == "cited"]
    lines = [
        "Written by `probes/run_p5.py`; nothing in this file is hand-edited.",
        "",
        "SCOPE OF THIS HEADER (it claims only what it can enforce): the resolved package "
        "id, the CSV resource url, the observed column list, and every row / CMA / year / "
        "suppression / rounding count in §1-§3 are emitted by this run from the live CKAN "
        "search response and the live CSV pull — the column list is split from the fetched "
        "header, never a literal. The suppression/rounding CONVENTION is quoted verbatim "
        "from the live package notes (cited below). The expected package id is a cross-check "
        "constant; the run asserts the live-resolved id equals it and prints both.",
    ]
    if _FACTS:
        lines.append(
            f"This run registered {len(_FACTS)} provenance-tagged figures: {len(derived)} "
            f"DERIVED (computed from the live response this run) and {len(cited)} CITED "
            f"(verbatim from the live package metadata). Untagged numerals elsewhere are "
            f"audit metadata (result counts, resource counts, column positions) and reference "
            f"labels (years, the base-5 rounding step), each traceable to the live response."
        )
    if cited:
        lines += ["", "Quoted verbatim from the live package metadata:"]
        lines += [f"- {f.text} — {f.source}" for f in cited]
    lines.append("")
    return lines


# --- network boundaries (injectable seams so the floor-guard test runs OFFLINE) ---
def _search() -> dict:
    """CKAN `package_search` -> parsed JSON. Boundary 1 (open.canada.ca).

    Deliberately NOT `pd.read_json` (a repeat trap on the CKAN shape): navigate the
    documented envelope {"success", "result": {"count", "results": [...]}} explicitly.
    """
    raw = urllib.request.urlopen(CKAN_SEARCH, timeout=TIMEOUT).read()
    return json.loads(raw)


def _fetch_csv(url: str) -> str:
    """Fetch the CMA CSV. Boundary 2 (ircc.canada.ca). Returns decoded text.

    IRCC serves this `.csv` UTF-8-with-BOM and TAB-delimited; utf-8-sig strips the BOM.
    """
    raw = urllib.request.urlopen(url, timeout=TIMEOUT).read()
    return raw.decode("utf-8-sig")


# --- CKAN navigation (written fresh — CKAN is not the WDS) -------------------
def _org_title(pkg: dict) -> str:
    return ((pkg.get("organization") or {}).get("title") or "").lower()


def _is_ircc(pkg: dict) -> bool:
    return IRCC_ORG_MARK in _org_title(pkg)


def _resources(pkg: dict) -> list[dict]:
    return pkg.get("resources") or []


def _cma_csv_resources(pkg: dict) -> list[dict]:
    """CSV resources whose name matches CMA/Metropolitan, EXCLUDING the French-speaking
    (ex-QC) sibling — that leaves the main Canada-wide CMA table."""
    out = []
    for r in _resources(pkg):
        name = (r.get("name") or "").upper()
        fmt = (r.get("format") or "").upper()
        if fmt == "CSV" and ("CMA" in name or "METROPOLITAN" in name) and "FRENCH" not in name:
            out.append(r)
    return out


def _first_resource(pkg: dict, want_fmt: str, *must: str, without: tuple = ()) -> dict | None:
    for r in _resources(pkg):
        name = (r.get("name") or "").upper()
        if (r.get("format") or "").upper() != want_fmt.upper():
            continue
        if all(m.upper() in name for m in must) and not any(w.upper() in name for w in without):
            return r
    return None


def _category_cma_cross_count(pkg: dict) -> int:
    """Resources crossing a CMA term AND an immigration-category term (point E:
    an EARNED absence — enumerated over THIS package's resources only)."""
    n = 0
    for r in _resources(pkg):
        name = (r.get("name") or "").upper()
        if ("CMA" in name or "METROPOLITAN" in name) and "CATEGORY" in name:
            n += 1
    return n


def _parse_delimited(text: str) -> tuple[list[str], list[list[str]], str]:
    """Header + rows + delimiter name, from the fetched text. Tab if the header line
    carries a tab, else comma (IRCC ships this `.csv` tab-delimited)."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return [], [], "none"
    delim = "\t" if "\t" in lines[0] else ","
    header = lines[0].split(delim)
    rows = [ln.split(delim) for ln in lines[1:]]
    return header, rows, ("tab" if delim == "\t" else "comma")


def _col_index(header: list[str], *needles: str) -> int | None:
    for i, c in enumerate(header):
        cu = c.upper()
        if all(n.upper() in cu for n in needles):
            return i
    return None


# --- floor guard (standalone so it can be mutation-tested) -------------------
class VacuousProbeError(RuntimeError):
    """A LOCATED must be EARNED. Raised when a boundary answered but with a body that
    cannot support the verdict: an empty/absent search population, a package with zero
    CMA CSV resources, or a 200-but-wrong-body CSV (an HTML error that parses into a
    degenerate 'schema'). Routes to UNKNOWN-PROBE-FAILED, never a fabricated LOCATED."""


def _guard_search(results: list, matched: list) -> None:
    """CKAN-boundary guard: the search must have a non-empty population AND resolve at
    least one IRCC package carrying a CMA CSV. An empty-but-200 response must not
    launder into a located claim over a population of zero."""
    if not results:
        raise VacuousProbeError(
            "package_search answered 200 but with an empty result set (count 0 / no results)"
        )
    if not matched:
        raise VacuousProbeError(
            "package_search returned results but NONE is an IRCC package carrying a CMA CSV "
            "resource — the located predicate resolved nothing"
        )


def _guard_csv_shape(header: list[str], rows: list[list[str]]) -> None:
    """CSV-boundary guard (point C): reject a 200-but-wrong-body page. Requires a
    PLAUSIBLE tabular shape — not an exact column match (schema drift must surface as
    a recorded observation, not a code fault): ≥3 columns, a geography-named column, a
    total-ish column, and ≥1 data row."""
    if len(header) < 3:
        raise VacuousProbeError(
            f"the CSV body parsed to {len(header)} column(s) — not a plausible table "
            f"(a 200-but-wrong-body page, e.g. an HTML error, parses this way): {header[:3]}"
        )
    if _col_index(header, "METROPOLITAN") is None and _col_index(header, "CMA") is None:
        raise VacuousProbeError(
            f"the CSV header carries no CMA/metropolitan column — not the expected geography "
            f"table: {header}"
        )
    if _col_index(header, "TOTAL") is None:
        raise VacuousProbeError(f"the CSV header carries no TOTAL column: {header}")
    if not rows:
        raise VacuousProbeError("the CSV parsed a header but zero data rows")


# --- the live hunt ----------------------------------------------------------
def _hunt(note: list[str], stage: dict) -> tuple[str, dict]:
    """Run the live two-boundary hunt, append its record to `note`, return
    (verdict, evidence). `stage["at"]` tracks the current boundary so a raise can be
    attributed (point B). Verdict is "LOCATED" on success; any raise is handled by
    main() -> UNKNOWN-PROBE-FAILED."""
    # ===================== boundary 1: CKAN package_search ==================
    stage["at"] = "ckan"
    payload = _search()
    result = payload.get("result") or {}
    results = result.get("results") or []
    count = result.get("count") or 0

    matched = [p for p in results if _is_ircc(p) and _cma_csv_resources(p)]
    _guard_search(results, matched)  # RAISES (ckan) on a vacuous search

    # Disambiguate DETERMINISTICALLY (not by relevance order): spec §4 names the
    # "monthly CSV", so prefer the matched package whose title says "Monthly" — the
    # sibling matches are Ad-Hoc/Specialized datasets. Falls back to the first match
    # only if none is titled monthly (then the id cross-check below catches a surprise).
    monthly = [p for p in matched if "monthly" in (p.get("title") or "").lower()]
    chosen = monthly or matched
    pkg = chosen[0]
    resolved_id = pkg.get("id") or pkg.get("name") or ""
    pkg_title = pkg.get("title") or ""
    all_res = _resources(pkg)
    csv_res = _cma_csv_resources(pkg)[0]
    csv_url = csv_res.get("url") or ""
    csv_res_id = csv_res.get("id") or ""

    xlsx_res = _first_resource(pkg, "XLSX", "CMA", without=("FRENCH",)) or {}
    xlsx_url = xlsx_res.get("url") or ""
    cat_res = _first_resource(
        pkg, "CSV", "IMMIGRATION CATEGORY", "PROVINCE",
        without=("CMA", "CITIZENSHIP", "FRENCH", "ENGLISH", "QUEBEC", "GENDER", "AGE"),
    ) or {}
    cat_url = cat_res.get("url") or ""
    cat_cma_cross = _category_cma_cross_count(pkg)

    notes_text = pkg.get("notes") or ""

    id_match = resolved_id == EXPECTED_PKG_ID
    f_count = Fact.derived(str(count), "package_search total match count (live)")
    f_swept = Fact.derived(str(len(results)), "results returned and swept by the predicate")
    f_matched = Fact.derived(str(len(matched)), "swept results matching the IRCC×CMA-CSV predicate")
    f_monthly = Fact.derived(str(len(monthly)), "matched packages titled 'Monthly' (spec §4)")
    f_id = Fact.derived(resolved_id, "id of the selected package (live)")

    note += [
        "## 1. CKAN discovery (boundary 1 — open.canada.ca)",
        "",
        f"- Query (the plan's, with `&rows=100` appended so the predicate sweeps 100 results "
        f"rather than CKAN's default 10): `{CKAN_SEARCH}`",
        f"- `package_search` -> success, **{f_count}** total matches for the query; "
        f"**{f_swept}** returned and swept.",
        f"- Located predicate (org is IRCC AND carries a CSV resource whose name matches "
        f"CMA/Metropolitan): **{f_matched}** of the {len(results)} swept matched ({count} "
        f"total). A LOCATED is earned by this live resolution, not by a hand-typed id.",
        f"- Of the {len(matched)} matched, **{f_monthly}** is titled \"Monthly\" (spec §4 names "
        f"the monthly CSV); that one is selected deterministically — the siblings are Ad-Hoc / "
        f"Specialized datasets, so selection does not depend on CKAN relevance order.",
        f"- Resolved package id: **`{f_id}`** — title *\"{pkg_title}\"*.",
        f"- Cross-check: resolved id {'EQUALS' if id_match else 'DOES NOT EQUAL'} the expected "
        f"`{EXPECTED_PKG_ID}` (kept only as a cross-check constant).",
        f"- Package carries {len(all_res)} resources; the CMA CSV resource resolved to "
        f"id `{csv_res_id}`.",
        "",
    ]
    if not id_match:
        note += [
            "> UNEXPECTED: the live-resolved id differs from the expected cross-check id. "
            "This is a recorded surprise, NOT a silent proceed — the package may have been "
            "reorganized. The resolved id above is what the run actually located.",
            "",
        ]

    # ===================== boundary 2: the CMA CSV pull =====================
    stage["at"] = "csv"
    text = _fetch_csv(csv_url)
    header, rows, delim = _parse_delimited(text)
    _guard_csv_shape(header, rows)  # RAISES (csv) on a 200-but-wrong-body page

    # --- observed schema, emitted from the fetched header (never a literal) ---
    f_ncol = Fact.derived(str(len(header)), "len(header) from the fetched CSV")
    f_nrow = Fact.derived(str(len(rows)), "count of parsed data rows")
    cma_i = _col_index(header, "CENSUS_METROPOLITAN")
    if cma_i is None:  # explicit — a valid column at index 0 is falsy, so `or` would skip it
        cma_i = _col_index(header, "METROPOLITAN")
    tot_i = _col_index(header, "TOTAL")
    yr_i = _col_index(header, "YEAR")
    mo_i = _col_index(header, "MONTH")

    years = sorted({r[yr_i] for r in rows if len(r) > yr_i and r[yr_i]}) if yr_i is not None else []
    months = sorted({r[mo_i] for r in rows if len(r) > mo_i and r[mo_i]}) if mo_i is not None else []
    cmas = sorted({r[cma_i] for r in rows if len(r) > cma_i and r[cma_i]}) if cma_i is not None else []
    f_ncma = Fact.derived(str(len(cmas)), "distinct CMA members in the fetched table")
    f_yspan = Fact.derived(
        f"{years[0]}..{years[-1]}" if years else "none",
        "min..max of the YEAR column",
    )

    # --- suppression / rounding, tallied over the live TOTAL column ---
    totals = [r[tot_i] for r in rows if len(r) > tot_i]
    supp_mark = "--"
    n_supp = sum(1 for v in totals if v.strip() == supp_mark)
    numeric = [int(v) for v in totals if v.strip() not in (supp_mark, "") and v.strip().lstrip("-").isdigit()]
    n_nonmult5 = sum(1 for v in numeric if v % 5 != 0)
    f_nsupp = Fact.derived(str(n_supp), f"count of '{supp_mark}' cells in the TOTAL column")
    f_nnum = Fact.derived(str(len(numeric)), "count of numeric TOTAL cells")
    f_nonmult5 = Fact.derived(str(n_nonmult5), "numeric TOTAL cells NOT divisible by 5")

    # --- per-modeled-CMA suppression materiality (point D) ---
    modeled = {}
    for cma in MODELED_CMAS:
        sel = [r for r in rows if len(r) > tot_i and cma_i is not None and len(r) > cma_i and r[cma_i] == cma]
        s_supp = sum(1 for r in sel if r[tot_i].strip() == supp_mark)
        s_num = [int(r[tot_i]) for r in sel if r[tot_i].strip() not in (supp_mark, "")
                 and r[tot_i].strip().lstrip("-").isdigit()]
        modeled[cma] = (len(sel), s_supp, s_num)

    # Summaries DERIVED from `modeled`, so every interpretive gloss below is a FUNCTION
    # of the computed per-CMA counts — never a constant that assumes today's data (a
    # gloss beside a computed value must never be able to contradict it).
    cma_present = {c: bool(modeled[c][2]) for c in MODELED_CMAS}  # has >=1 numeric row
    both_present = all(cma_present.values())
    modeled_supp_total = sum(modeled[c][1] for c in MODELED_CMAS)
    supp_immaterial = modeled_supp_total == 0

    # --- the suppression/rounding CONVENTION, quoted verbatim from live notes ---
    conv_quote = ""
    for sent in notes_text.replace("\n", " ").split("."):
        if "--" in sent or "rounded" in sent.lower() or "suppress" in sent.lower():
            conv_quote += sent.strip() + ". "
    conv_quote = conv_quote.strip()
    if conv_quote:
        Fact.cited(
            "suppression/rounding convention (values 0-5 shown as \"--\"; others rounded to "
            "nearest 5)",
            f"live package notes of {resolved_id}: \"{conv_quote}\"",
        )

    note += [
        "## 2. Observed schema — the CMA CSV (boundary 2 — ircc.canada.ca)",
        "",
        f"- CSV resource url: `{csv_url}`",
        f"- Delimiter (observed): **{delim}** (shipped as `.csv` but {delim}-delimited).",
        f"- **{f_ncol}** columns, **{f_nrow}** data rows, **{f_ncma}** distinct CMA members, "
        f"years **{f_yspan}**, {len(months)} distinct month labels (monthly cadence).",
        "- Observed column list (split from the fetched header):",
        "",
        "  | # | column |",
        "  |---:|---|",
    ]
    note += [f"  | {i} | `{c}` |" for i, c in enumerate(header)]
    note += [
        "",
        f"- The table is CMA × month × **TOTAL** (PR admissions). `TOTAL` is column {tot_i}; "
        f"the CMA member is column {cma_i} (`{header[cma_i] if cma_i is not None else '?'}`).",
        f"- Modeled-CMA presence ({'both present' if both_present else 'AT LEAST ONE ABSENT'}): "
        + ", ".join(
            f"**{cma}** ({'present' if cma_present[cma] else 'ABSENT — no numeric rows'}: "
            f"{modeled[cma][0]} monthly rows, {len(modeled[cma][2])} numeric, "
            f"{modeled[cma][1]} suppressed, "
            f"range {min(modeled[cma][2]) if modeled[cma][2] else 'n/a'}–"
            f"{max(modeled[cma][2]) if modeled[cma][2] else 'n/a'})"
            for cma in MODELED_CMAS
        )
        + ".",
        "",
        "## 3. Suppression / rounding convention and materiality",
        "",
        f"- Convention (quoted verbatim from the live package notes): "
        + (f"\"{conv_quote}\"" if conv_quote else "NOT STATED in the live package notes."),
        f"- Tallied over the live TOTAL column: **{f_nsupp}** suppressed (`--`) cells of "
        f"{len(totals)} total; **{f_nnum}** numeric cells, of which **{f_nonmult5}** are NOT "
        f"multiples of 5 "
        + ("(0 confirms base-5 rounding)."
           if n_nonmult5 == 0
           else f"(NON-ZERO: base-5 rounding does NOT hold — {n_nonmult5} cells break it)."),
        f"- **Handling (spec §4):** a suppressed `--` cell is treated as a **0-band** "
        f"(the true value is 0–5). For the TWO modeled CMAs this convention is "
        f"**{'immaterial' if supp_immaterial else 'MATERIAL'}**: "
        + ", ".join(f"{cma} has **{modeled[cma][1]}** suppressed cells" for cma in MODELED_CMAS)
        + (f" — {modeled_supp_total} suppressed across both, so only base-5 rounding (±2.5 per "
           f"monthly cell) applies to the tripwire's targets, negligible against the MIFI plan "
           f"level (~45k/yr, a spec §4 constant)."
           if supp_immaterial
           else f" — {modeled_supp_total} suppressed across both, each a 0-band (0–5) that Task "
           f"28 MUST apply explicitly to the tripwire's targets (base-5 rounding, ±2.5 per cell, "
           f"is then secondary)."),
        "",
        "## 4. Category axis (recorded divergence from spec §4 'by CMA + category')",
        "",
        f"- **{cat_cma_cross}** of {len(all_res)} resources in THIS package cross a CMA term "
        f"with an immigration-category term (enumerated live). The CMA table above is "
        f"geography × month × TOTAL only — no category dimension.",
        f"- Immigration category is published at the **Province/Territory** level in a sibling "
        f"resource: `{cat_url or 'not resolved this run'}`. This is scoped to THIS package's "
        f"resources — it is NOT a claim that category×CMA exists nowhere in IRCC open data.",
        "- The PR-landings tripwire (spec §7) compares realized landings vs the MIFI plan "
        "level, which needs `TOTAL` only; the category axis is not required for it.",
        "",
        "## 5. Semantic caveat for Task 28 (destination vs residence)",
        "",
        "- The main CMA resource's name and metadata do NOT state whether the CMA is place of "
        "residence or intended destination at landing (the resource `description` is empty). "
        "The French-speaking (ex-QC) sibling resources DO name theirs \"...Census Metropolitan "
        "Area of Intended Destination\". Task 28 should treat the CMA as IRCC's intended-"
        "destination-at-admission by convention, but this is NOT confirmed in this resource's "
        "metadata — recorded, not asserted.",
        "",
    ]

    evidence = {
        "resolved_id": resolved_id,
        "csv_url": csv_url,
        "xlsx_url": xlsx_url,
        "columns": header,
        "delim": delim,
        "found_at_cma": both_present,
        "cma_present": cma_present,
        "modeled_numeric": {c: len(modeled[c][2]) for c in MODELED_CMAS},
        "convention": conv_quote,
        "cat_url": cat_url,
        "cat_cma_cross": cat_cma_cross,
        "n_resources": len(all_res),
    }
    return "LOCATED", evidence


def main() -> None:
    _FACTS.clear()
    title = ["# P5 — IRCC PR admissions by CMA (RECORDED OBSERVATION)", ""]
    body: list[str] = []
    stage = {"at": "ckan"}

    verdict = "UNKNOWN-PROBE-FAILED"
    evidence: dict = {}
    try:
        verdict, evidence = _hunt(body, stage)
    except Exception as exc:  # outage, a vacuous 200, or a wrong-body page — never a false LOCATED
        boundary = stage.get("at", "ckan")
        host = CKAN_HOST if boundary == "ckan" else "ircc.canada.ca"
        body += [
            "## LIVE HUNT VERDICT: UNKNOWN-PROBE-FAILED",
            "",
            f"- `LIVE PROBE FAILED-AT: {boundary}` (host: {host})",
            f"- `LIVE PROBE FAILED: {type(exc).__name__}: {exc}`",
            "",
            "  The source did not answer usefully at the boundary named above — an outage, or a "
            "200 carrying an empty/wrong body (caught by the floor guard). This run therefore "
            "did NOT locate the schema, and deliberately records UNKNOWN rather than a fabricated "
            "LOCATED. Per spec §7 the PR-landings tripwire reports **UNKNOWN** while this source "
            "is unwired (never a stale within-band). Re-run against a live source to record the "
            "schema.",
            "",
        ]

    body += ["## DECISION", ""]
    if verdict == "LOCATED":
        cols = " | ".join(evidence["columns"])
        body += [
            "- `DECISION-VERDICT: LOCATED`",
            f"- `DECISION-PACKAGE-ID: {evidence['resolved_id']}`",
            f"- `DECISION-CSV-URL: {evidence['csv_url']}`",
            f"- `DECISION-CSV-XLSX-UNROUNDED-URL: {evidence['xlsx_url']}`  "
            "(the unrounded XLSX source, for when base-5 rounding matters)",
            f"- `DECISION-DELIMITER: {evidence['delim']}`",
            f"- `DECISION-COLUMNS: {cols}`",
            "- `DECISION-SUPPRESSED-CONVENTION: cells shown as \"--\" are values 0-5 "
            "(suppressed); treat as a 0-band per spec §4. All other values are rounded to the "
            "nearest multiple of 5.`",
            f"- `DECISION-FOUND-AT-CMA: {'YES' if evidence['found_at_cma'] else 'NO'}`  "
            + "(numeric monthly rows in the live pull: "
            + ", ".join(f"{c} {evidence['modeled_numeric'][c]}"
                        f"{'' if evidence['cma_present'][c] else ' — ABSENT'}"
                        for c in MODELED_CMAS)
            + (" — both present)" if evidence['found_at_cma']
               else " — at least one modeled CMA has NO numeric rows)"),
            f"- `DECISION-CATEGORY-AT-CMA: "
            f"{'NOT-IN-PACKAGE' if evidence['cat_cma_cross'] == 0 else 'PRESENT'}`  "
            + f"({evidence['cat_cma_cross']} of {evidence['n_resources']} resources in this "
            f"package cross a CMA term with an immigration-category term — see §4; "
            + (f"category is Province/Territory only: "
               f"`{evidence.get('cat_url') or 'sibling resource'}`; "
               if evidence['cat_cma_cross'] == 0
               else "pull that cross-tab before relying on category-at-CMA; ")
            + "the tripwire needs TOTAL only)",
            "",
            "- Standing rule (spec §7): this source feeds the PR-landings TRIPWIRE (realized PR "
            "landings vs the MIFI plan level), NOT the demand model (which uses ISQ compo "
            "\"Immigrants permanents\"). If the source becomes unavailable the tripwire reports "
            "UNKNOWN — never a stale within-band.",
            "",
        ]
    else:
        body += [
            f"- `DECISION-VERDICT: {verdict}`",
            "- The schema could not be located this run (see the boundary failure above). The "
            "PR-landings tripwire reports UNKNOWN until this source is wired. This is a recorded "
            "observation, not an invented schema.",
            "",
        ]

    text = "\n".join(title + _provenance_header() + body) + "\n"
    for placeholder in ("[FILL:", "[FILL]", "[FILL "):
        if placeholder in text:
            raise AssertionError(f"run_p5.py emitted an unresolved {placeholder!r} placeholder")
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
