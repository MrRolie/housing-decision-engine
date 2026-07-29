"""P6 — MRC-level ISQ source hunt for couronne-nord precision (spec §11 item 6).

WHO USES THIS (spec §8, Geography junction): the `Geography` enum carries
LANAUDIERE_RA14_PROXY / LAURENTIDES_RA15_PROXY / MONTEREGIE_RA16_PROXY, flagged `ra_proxy`
— exact administrative-region data standing in for the finer couronne geography demoflow
would rather model. §8 records the reason: *"couronne-nord precision is DEFERRED (no MRC
workbook exists — probed 404, 2026-07-21; plan task hunts an MRC source)"*. This probe is
that hunt. **v0 PROCEEDS REGARDLESS** — a find enables a v1 Geography-enum extension only,
never a v0 change (that sentence is written unconditionally, so no gate may rest on it).

THE DISCRIMINATOR, stated before the hunt so the verdict cannot drift to fit the answer.
A LOCATED needs THREE pieces of evidence about ONE resource, all computed here:
  (a) a resource URL resolved from a swept population — never a guessed slug;
  (b) the OBSERVED HTTP status of a real request to it;
  (c) a BODY-SHAPE check proving the bytes really are MRC-level — the file is opened, its
      `MRC` header cell located, and its geography labels counted and name-searched.
A bare 200 FAILS: this host answers 200 with an HTML page body for some paths and 404 with
a 45KB HTML body for others, so status alone cannot tell a workbook from an error page.

THE SEARCHED POPULATION (Ruling R7 — a NOT-FOUND is unearned without one). Two
boundaries, each enumerated, so an absence claim is scoped to something real:
  * BOUNDARY A — Données Québec CKAN (`donneesquebec.ca`). The ISQ organization slug is
    RESOLVED LIVE from `organization_list` by a title predicate, never typed: a guessed
    slug (`organization:institut-de-la-statistique-du-quebec`) returns zero, and a zero
    from a wrong slug is not an absence.
  * BOUNDARY B — ISQ's own product pages / full-edition downloads
    (`statistique.quebec.ca`), which is what §11.6 actually asks for. Its `sitemap.xml`
    enumerates the site, so the sweep runs over a real population rather than two guesses.
Every absence claim below is scoped to "not among the N locs and the M packages swept" —
never "no MRC source exists".

METHOD IS LOAD-BEARING HERE, so this run MEASURES it instead of asserting it: §3 issues a
HEAD and a GET against the SAME url and prints both statuses. The plan body's hunt is
HEAD-only, so if the two disagree, a HEAD-based hunt can report a live workbook as absent.
Every request this probe makes for evidence is a GET; the HEAD is issued solely as the
measured comparison, and the note's sentence about it is a function of the two observed
codes — not a claim that survives them agreeing.

FLOOR GUARD (NS #1 — a verification gate must REFUSE when it cannot verify). An empty
sitemap, an empty CKAN catalogue, a sweep over an unswept population, or a candidate that
answers 200 with a non-workbook body must NOT become a NOT-FOUND or a LOCATED. Each raises
`VacuousProbeError` -> UNKNOWN-PROBE-FAILED with the failing boundary recorded. A NOT-FOUND
in particular requires BOTH populations to have been swept and to be NON-EMPTY.

ANTI-FABRICATION (the cardinal discipline). Every value reported as observed is emitted by
THIS run: the resolved org slug, the catalogue and sitemap sizes, the swept and eligible
candidate lists, each candidate's observed status / content-type / declared length / magic
bytes, the opened workbook's sheet names, header position, geography-label count and label
list, its scenario labels, and the per-target couronne search. The verbatim quotes are
CITED, resolved from live responses by predicate.

Run:  cd demoflow && uv run python probes/run_p6.py
"""

import io
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

# Flat, NOT `probes._wds`: probes/ is deliberately not a package, so in script mode
# sys.path[0] IS probes/ and this resolves natively. See probes/_wds.py.
from _wds import Fact, new_run, provenance_header

# --- boundary A: Données Québec CKAN (the enumerable open-data catalogue) ------------
CKAN_ACTION = "https://www.donneesquebec.ca/recherche/api/3/action"
CKAN_ORGS = f"{CKAN_ACTION}/organization_list?all_fields=true&limit=1000"
CKAN_COUNT = f"{CKAN_ACTION}/package_search?rows=0"
CKAN_ORG_SEARCH = CKAN_ACTION + "/package_search?fq=organization:{slug}&rows=100"
CKAN_TERM_SEARCH = (CKAN_ACTION + "/package_search?q=MRC+projection+population"
                    "+perspectives+demographiques&rows=100")
# The ISQ organization is resolved by THIS predicate over the live `title` field. A slug is
# never assumed: `organization:institut-de-la-statistique-du-quebec` (the obvious guess)
# returns 0 packages, and a zero from a wrong slug would be a fabricated absence.
CKAN_ORG_TITLE_MARK = "institut de la statistique"

# --- boundary B: ISQ's own site (product pages / full-edition downloads) -------------
ISQ_SITEMAP = "https://statistique.quebec.ca/sitemap.xml"
ISQ_HOST = "statistique.quebec.ca"
# The sitemap lists `/fr/fichier/<slug>` and `/en/fichier/<slug>` for the SAME workbook.
# When the sweep collapses them, keep the `/fr/` one: the ISQ workbooks demoflow already
# pins are `/fr/` urls, so the url this note publishes stays on the repo's own convention.
PREFERRED_LANG_PATH = "/fr/"

# The plan body's two GUESSED slugs, probed live so the "the 404 was the slug convention,
# not the data" statement in §4 is a COMPUTED comparison against the located resource's own
# observed status — not a retelling of what someone recorded in 2026-07.
PLAN_GUESSED_SLUGS = (
    "https://statistique.quebec.ca/fr/fichier/pop-as-mrc-base.xlsx",
    "https://statistique.quebec.ca/fr/fichier/pop-mrc-base.xlsx",
)

# --- the sitemap sweep predicate (stated before its result) --------------------------
# A candidate must be an .xlsx naming BOTH an MRC geography term and a population term:
# that is the SWEPT population. ELIGIBILITY additionally requires a PROJECTION term,
# because spec §8's junction consumes projected population by scenario — an estimates
# workbook is a different product. Both tiers are emitted, so every absence claim is scoped
# to the WIDER swept set rather than to the narrower eligible one.
MRC_TERMS = ("mrc", "municipalites-regionales-de-comte")
POPULATION_TERMS = ("population", "composantes-demographiques", "menages", "demographiques")
PROJECTION_TERMS = ("projet", "scenario", "perspectives-demographiques")

# The two ISQ workbook families demoflow already consumes at RMR level (the files committed
# with the grounding research: `pop-as-rmr-base.xlsx`, `compo-rmr-base.xlsx`). DECLARED here
# rather than asserted downstream, so the note's family attribution moves with this map
# instead of being a sentence about files nothing in this run inspected.
DEMOFLOW_RMR_FAMILY = {
    "pop-as-* (population by age and sex)": ("population", "age", "sexe"),
    "compo-* (projected demographic components)": ("composantes-demographiques",),
}

# The couronne MRCs, DECLARED per spec §8's three `ra_proxy` rows, each keyed by the RA
# NUMBER the spec proxies. Declared here, not inferred — and deliberately falsifiable: the
# opened workbook carries its OWN administrative-region column, so the declared RA number is
# checked against the code the live response puts beside each MRC. Flip a key to RA99 and
# the corroboration stops, instead of the note republishing a false grouping.
#
# What the declaration does NOT claim, and what this run does not compute: that these MRCs
# EXHAUST their RA, or that they exactly compose the Montréal RMR's couronne. The per-target
# search establishes membership, never partition.
COURONNE_MRC_BY_RA = {
    "RA14 Lanaudière": ("Les Moulins", "L'Assomption"),
    "RA15 Laurentides": ("Thérèse-De Blainville", "Deux-Montagnes", "Mirabel",
                         "La Rivière-du-Nord"),
    "RA16 Montérégie": ("Roussillon", "Marguerite-D'Youville", "La Vallée-du-Richelieu",
                        "Vaudreuil-Soulanges"),
}

# The geography header cell is matched by PREFIX, not by equality and not by substring.
# Measured reason for each rejection: equality misses the 2016-2041 edition, whose header
# cell reads "MRC par région administrative"; a substring test matches the CAPTION row
# ("Population projetée des MRC du Québec, …") and would count zero labels below it. A
# prefix admits both real headers and excludes both captions.
MRC_HEADER_PREFIX = "mrc"
# The administrative-region column, when the edition publishes one (the A2021 components
# edition heads it `RA1`). This is the axis spec §8's RA14/15/16 proxies turn on, so it is
# SEARCHED FOR and its absence is reported as an absence — never assumed either way.
RA_HEADER_PATTERN = re.compile(r"^ra\s*\d*$")
# Both spellings, because these workbooks mix accented and unaccented headers and this file
# does not normalise accents away (doing so would also fold the MRC labels, which are
# compared by exact name).
RA_HEADER_MARKS = ("région administrative", "region administrative")
SCENARIO_HEADER_MARKS = ("scénario", "scenario")
HEADER_SCAN_ROWS = 12
# These geography columns are NOT homogeneous: ISQ interleaves administrative-region
# SUBTOTAL rows, published in a `NN  Name` form ("01  Bas-Saint-Laurent"), among the MRC
# rows. The label count alone would therefore read as an MRC count and be wrong. This
# pattern splits the two so the decomposition is emitted instead of the raw total.
AGGREGATE_LABEL_PATTERN = re.compile(r"^\d{2}\s")
# ZIP local-file-header magic. An HTML error page served at 200 — the wrong-body case R7
# names — cannot start with these four bytes.
XLSX_MAGIC = b"PK\x03\x04"
PREFIX_BYTES = 8

OUT = Path(__file__).resolve().parent / "P6-mrc-isq-hunt.md"
CKAN_TIMEOUT = 120
ISQ_TIMEOUT = 180  # the sitemap is ~13MB; WDS_TIMEOUT governs a different boundary


# --- this note's provenance prose (the shared header skeleton lives in _wds) ---------
# The filename this note must attribute itself to. DERIVED from __file__, never typed:
# `written_by` is the one header field a copy-pasted call block carries forward silently —
# a probe cloned from run_p5b.py would publish "Written by run_p5b.py" over its own
# computed body, exactly the untied claim this registry exists to stop.
_WRITTEN_BY = Path(__file__).name
_SCOPE = ("SCOPE OF THIS HEADER (it claims only what it can enforce): the resolved ISQ "
          "organization slug, the CKAN catalogue and swept-package counts, the sitemap loc "
          "and .xlsx counts, the swept and eligible candidate lists, every candidate's "
          "observed HTTP status / content-type / declared length / magic-byte result, the "
          "HEAD-vs-GET comparison, the opened workbook's sheet names, header position, "
          "geography-label count and label list, its scenario column, the per-target "
          "couronne name search AND the per-target administrative-region corroboration are "
          "ALL emitted by this run from live responses. The quoted strings are verbatim "
          "from live responses. Every absence claim is scoped to what was actually swept — "
          "never to what exists. What this run does NOT compute, and therefore does not "
          "claim: that the declared couronne MRCs EXHAUST RA14/15/16, or that they exactly "
          "compose the Montréal RMR's couronne — the RA check establishes MEMBERSHIP, not a "
          "partition. Nor does it claim anything about the candidates it did not open: "
          "exactly ONE workbook is opened and shape-checked, and the §2 table's other rows "
          "carry status-and-prefix evidence only.")
_CITED_LABEL = "Quoted verbatim from the live responses:"


def _summary(*, total: int, derived: int, cited: int) -> str:
    """The provenance sentence, sized to what this run actually registered."""
    return (
        f"This run registered {total} provenance-tagged figures: {derived} DERIVED "
        f"(computed from the live responses of this run) and {cited} CITED (verbatim from "
        f"a live response body). Untagged numerals elsewhere are audit metadata (candidate "
        f"counts, byte lengths, row/column positions, HTTP status codes) and reference "
        f"labels (slugs, urls, sheet names), each traceable to the live response this run "
        f"read."
    )


# --- network boundaries (injectable seams so the floor-guard test runs OFFLINE) ------
def _ckan_get(url: str) -> dict:
    """A CKAN action endpoint -> parsed JSON. Boundary `ckan-*` (donneesquebec.ca).

    Deliberately NOT `pd.read_json` (the repeat trap this probe family keeps hitting on
    the CKAN shape): navigate the documented envelope
    {"success", "result": {"count", "results": [...]}} explicitly.
    """
    raw = urllib.request.urlopen(url, timeout=CKAN_TIMEOUT).read()
    return json.loads(raw)


def _sitemap() -> str:
    """`sitemap.xml` -> decoded text. Boundary `isq-sitemap` (statistique.quebec.ca)."""
    raw = urllib.request.urlopen(ISQ_SITEMAP, timeout=ISQ_TIMEOUT).read()
    return raw.decode("utf-8", errors="replace")


def _probe_url(url: str, *, method: str = "GET", nbytes: int = PREFIX_BYTES) -> dict:
    """Observe one url: status, content-type, declared length, first `nbytes` bytes.

    Only a PREFIX is read, then the connection closes — so a 17MB candidate costs a
    handshake, not a download, while still yielding real magic bytes.

    `urllib.error.HTTPError` is caught and REPORTED AS THE OBSERVED STATUS: a 404 is an
    answer, not a probe failure, and this hunt's whole job is to record which URLs answer
    what. Every other exception propagates — a DNS failure or a timeout is NOT an observed
    status and must not be laundered into one.
    """
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=ISQ_TIMEOUT) as resp:
            return {
                "status": resp.status,
                "ctype": (resp.headers.get("Content-Type") or "").split(";")[0].strip(),
                "length": resp.headers.get("Content-Length") or "",
                "prefix": resp.read(nbytes) if nbytes else b"",
                "error": "",
            }
    except urllib.error.HTTPError as exc:
        return {"status": exc.code,
                "ctype": (exc.headers.get("Content-Type") or "").split(";")[0].strip()
                if exc.headers else "",
                "length": (exc.headers.get("Content-Length") or "") if exc.headers else "",
                "prefix": b"", "error": f"HTTPError {exc.code}"}


def _download(url: str) -> bytes:
    """Fetch one candidate in full, for the body-shape check. Boundary `isq-file`."""
    return urllib.request.urlopen(url, timeout=ISQ_TIMEOUT).read()


def _workbook_rows(data: bytes, *, max_rows: int = 0) -> tuple[list[str], list[tuple]]:
    """(sheet names, rows of the FIRST sheet) from xlsx bytes. Boundary `isq-file`.

    `openpyxl` directly, NOT pandas: nothing here needs a DataFrame, and the raw cell grid
    is what the header search and the label count read. Raises on a non-xlsx body — which
    is a REFUSAL, routed to UNKNOWN by the caller, never a silent empty result.
    """
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        ws = wb[wb.sheetnames[0]]
        rows = [r for r in ws.iter_rows(max_row=max_rows or None, values_only=True)]
        return list(wb.sheetnames), rows
    finally:
        wb.close()


# --- small computed helpers ---------------------------------------------------------
def _norm(text: object) -> str:
    """The ONE name-normalisation rule in this file (see run_p5b.py: two rules for one job
    is what a later probe copies wrongly)."""
    return str(text or "").strip().lower()


def _terms(text: str, terms) -> list[str]:
    low = _norm(text)
    return [t for t in terms if t in low]


def _slug(url: str) -> str:
    return url.rsplit("/", 1)[-1]


def _count_str(result: dict) -> str:
    """CKAN's total-match count, or an explicit marker when the key is absent.

    `result.get("count")` would print a bare `None` into the note if CKAN omitted the key —
    a missing measurement rendered as if it were one.
    """
    n = result.get("count")
    return str(n) if isinstance(n, int) else "an UNREPORTED number of"


def _pkg_text(pkg: dict) -> str:
    """Title + notes + every resource name and url, for predicate matching."""
    parts = [pkg.get("title") or "", pkg.get("notes") or ""]
    for r in pkg.get("resources") or []:
        parts += [r.get("name") or "", r.get("url") or ""]
    return " | ".join(parts)


def _locs(xml: str) -> list[str]:
    """Every `<loc>` in the sitemap, DEDUPED and sorted. The raw document repeats a url
    once per hreflang alternate, so an un-deduped count would overstate the population an
    absence claim is scoped to."""
    return sorted(set(re.findall(r"<loc>(.*?)</loc>", xml)))


def _find_header(rows: list[tuple]) -> tuple[int | None, int | None]:
    """(row, col) of the geography header cell, or (None, None) when the sheet has none.

    PREFIX match — see `MRC_HEADER_PREFIX` for the measured reason equality and substring
    both fail across the editions this hunt sweeps.
    """
    for r, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        for c, value in enumerate(row):
            if _norm(value).startswith(MRC_HEADER_PREFIX):
                return r, c
    return None, None


def _find_column(rows: list[tuple], header_row: int, predicate) -> tuple[int, str]:
    """(column index, header text) of the first cell in `header_row` satisfying `predicate`,
    or (-1, "") when the sheet publishes no such axis. -1 rather than None so the caller
    cannot confuse "absent" with column 0."""
    for c, value in enumerate(rows[header_row]):
        text = str(value).strip() if value is not None else ""
        if text and predicate(_norm(text)):
            return c, text
    return -1, ""


def _declared_ra_number(key: str) -> str:
    """`"RA14 Lanaudière"` -> `"14"`. Derived from the declaration's own key, so the number
    checked against the live response cannot drift from the key it is grouped under."""
    found = re.search(r"ra\s*(\d+)", key, re.IGNORECASE)
    return found.group(1) if found else ""


def _labels(rows: list[tuple], header_row: int, col: int) -> list[str]:
    """Distinct non-empty values below the header in the geography column, sorted."""
    out = set()
    for row in rows[header_row + 1:]:
        if col < len(row) and row[col] is not None and str(row[col]).strip():
            out.add(str(row[col]).strip())
    return sorted(out)


def _first_cell_matching(rows: list[tuple], needle: str, *, max_rows: int) -> str:
    """The first cell in the top `max_rows` whose text contains `needle`, verbatim."""
    for row in rows[:max_rows]:
        for value in row:
            if value is not None and needle in _norm(value):
                return str(value).strip()
    return ""


# --- floor guard (standalone so it can be mutation-tested) --------------------------
class VacuousProbeError(RuntimeError):
    """A verdict must be EARNED. Raised when a boundary answered but with a body that
    cannot support one: an empty sitemap, a candidate whose 200 carries a non-workbook
    body, a workbook with no MRC header or zero geography labels, or — for a NOT-FOUND —
    a searched population that was empty or never swept. Routes to UNKNOWN-PROBE-FAILED
    with the failing boundary, never a fabricated LOCATED and never a hollow NOT-FOUND."""


def _guard_sitemap(xml: str, locs: list[str]) -> None:
    """`isq-sitemap` guard: the ISQ-side population must EXIST before anything is claimed
    about it — a sweep over zero urls can neither locate nor rule out."""
    if not xml.strip():
        raise VacuousProbeError("sitemap.xml answered 200 but with an EMPTY body")
    if not locs:
        raise VacuousProbeError(
            "sitemap.xml answered 200 but parsed to ZERO <loc> entries — the ISQ-side sweep "
            "would run over an empty population"
        )


def _is_workbook_response(probe: dict) -> bool:
    """The CHEAP screen every eligible candidate passes through: a 200 whose first bytes are
    the ZIP magic. A bare 200 is not enough — this host serves HTML at 200 on some paths and
    a 45KB HTML body at 404 on others, so status alone cannot tell a workbook from an error
    page. Standalone so the screen and the deep guard below cannot drift apart."""
    return probe["status"] == 200 and probe["prefix"].startswith(XLSX_MAGIC)


def _guard_body(url: str, probe: dict, sheets: list[str], header_row: int | None,
                col: int | None, labels: list[str]) -> None:
    """`isq-file` guard — the one that keeps a LOCATED honest (see the mutation test).

    Which branches do the work, stated honestly because the mutation test grades them:

      * SAFETY-load-bearing — the three SHAPE branches (opened to at least one sheet, an
        MRC-named header cell found, that column carrying at least one label). Nothing else
        in the run inspects the opened bytes, so neutering this publishes a LOCATED whose
        geography evidence is an empty list. That is the mutation the test performs.
      * BACKSTOP only — the status and magic-byte branches. `_is_workbook_response` already
        screens both when `verified` is built, so on today's call path they cannot fire.
        They are kept because they state this function's PRECONDITION at the point that
        depends on it: a future pick rule that stopped screening would otherwise reach the
        `openpyxl` call with an HTML body and surface as a raw parse error rather than a
        refusal. They are not claimed to be doing work today.
    """
    if probe["status"] != 200:
        raise VacuousProbeError(
            f"the selected candidate {url} answered HTTP {probe['status']} — it cannot carry "
            f"the body-shape evidence a LOCATED requires"
        )
    if not probe["prefix"].startswith(XLSX_MAGIC):
        raise VacuousProbeError(
            f"the selected candidate {url} answered 200 but its first bytes are "
            f"{probe['prefix']!r}, not the {XLSX_MAGIC!r} workbook magic — a 200-but-wrong-body "
            f"page (this host serves HTML at 200), never a workbook"
        )
    if not sheets:
        raise VacuousProbeError(f"{url} opened but carries ZERO sheets")
    if header_row is None or col is None:
        raise VacuousProbeError(
            f"{url} opened but carries no cell beginning {MRC_HEADER_PREFIX!r} in its first "
            f"{HEADER_SCAN_ROWS} rows — nothing in this body identifies an MRC geography "
            f"column, so an MRC-level claim over it would be unearned"
        )
    if not labels:
        raise VacuousProbeError(
            f"{url}'s MRC column (row {header_row}, column {col}) carries ZERO labels — an "
            f"MRC-level answer over an empty column is unearned"
        )


def _guard_not_found(locs: list[str], eligible: list, verified: list, ckan: dict) -> None:
    """The NOT-FOUND guard — an ABSENCE claim needs a population that was actually swept,
    AND must not be standing in for a boundary that answered badly.

    R7: a zero-result sweep over an EMPTY catalogue, over a boundary that never answered, or
    a 200-but-wrong-body product page must each route to UNKNOWN, never NOT-FOUND. All three
    are checked here, so this single guard is the whole gate on an absence claim.

    Note the distinction the first check draws, because it is the one that decides whether
    NOT-FOUND means anything: ZERO eligible candidates is a real absence — the sweep looked
    and found nothing to look at. Eligible candidates that NONE verify is not an absence at
    all: the sweep found things and the boundary failed to serve them, which is exactly the
    wrong-body case. Collapsing the two would let an outage publish "no MRC source among the
    N swept" while N candidate urls sat in the table above it.
    """
    if eligible and not verified:
        raise VacuousProbeError(
            f"the sweep resolved {len(eligible)} eligible candidate(s) but NONE answered 200 "
            f"with a workbook body — that is a boundary serving wrong bodies (or refusing), "
            f"not an absence; a NOT-FOUND here would report the sweep's own failure as a "
            f"finding about ISQ's holdings"
        )
    if not locs:
        raise VacuousProbeError(
            f"the ISQ sitemap sweep ran over {len(locs)} loc(s) — a NOT-FOUND scoped to an "
            f"empty population is not an earned absence"
        )
    if not ckan["measured"]:
        raise VacuousProbeError(
            f"the CKAN boundary did not answer usefully ({ckan['why']}) — with only one of "
            f"the two searched populations swept, a NOT-FOUND would be scoped to a "
            f"population this run never enumerated"
        )
    if not ckan["n_catalogue"] or not ckan["n_swept"]:
        raise VacuousProbeError(
            f"the CKAN catalogue reported {ckan['n_catalogue']} package(s) and the sweep "
            f"enumerated {ckan['n_swept']} — an absence claim over an EMPTY catalogue is the "
            f"vacuous-absence shape, not a NOT-FOUND"
        )


# --- boundary A: Données Québec CKAN ------------------------------------------------
def _sweep_ckan(note: list[str]) -> dict:
    """Sweep the CKAN catalogue. Contributes the searched population a NOT-FOUND is scoped
    to; a failure here CANNOT demote a body-verified LOCATED (a located source is located),
    but it DOES block a NOT-FOUND — see `_guard_not_found`.

    Returns {"measured": bool, ...}; every failure is recorded as NOT MEASURED THIS RUN so
    an unswept catalogue can never read as a catalogue that was swept.
    """
    note += ["## 1. Boundary A — Données Québec CKAN (the enumerable open-data catalogue)",
             ""]
    out = {"measured": False, "why": "", "slug": "", "n_orgs": 0, "n_catalogue": 0,
           "n_swept": 0, "n_isq": 0, "n_match": 0, "matches": [], "quote": ""}
    try:
        orgs = (_ckan_get(CKAN_ORGS).get("result") or [])
        # The slug is RESOLVED, never typed. `organization:institut-de-la-statistique-du-quebec`
        # — the obvious guess — returns zero packages, and a zero from a wrong slug is a
        # fabricated absence, not a measurement.
        hits = sorted(
            (o.get("name") or "") for o in orgs
            if CKAN_ORG_TITLE_MARK in _norm(o.get("title"))
        )
        slug = hits[0] if hits else ""
        total = (_ckan_get(CKAN_COUNT).get("result") or {})
        n_catalogue = total.get("count") if isinstance(total.get("count"), int) else 0

        swept: dict[str, dict] = {}
        n_isq = 0
        if slug:
            isq_res = (_ckan_get(CKAN_ORG_SEARCH.format(slug=slug)).get("result") or {})
            for pkg in isq_res.get("results") or []:
                swept[pkg.get("id") or pkg.get("name") or ""] = pkg
            n_isq = len(swept)
        term_res = (_ckan_get(CKAN_TERM_SEARCH).get("result") or {})
        for pkg in term_res.get("results") or []:
            swept.setdefault(pkg.get("id") or pkg.get("name") or "", pkg)

        # The same two-term predicate the ISQ-side sweep uses, over title + notes + every
        # resource name and url — so the two boundaries' absence claims mean the same thing.
        matches = []
        for pkg in swept.values():
            text = _pkg_text(pkg)
            if _terms(text, MRC_TERMS) and _terms(text, PROJECTION_TERMS) \
                    and _terms(text, POPULATION_TERMS):
                matches.append({"title": pkg.get("title") or "",
                                "org": ((pkg.get("organization") or {}).get("name") or ""),
                                "n_res": len(pkg.get("resources") or [])})

        # A CITED corroboration, resolved BY PREDICATE from a live package's own notes: a
        # statement about ISQ's publication practice. It is NOT evidence about the file
        # opened in §3 — that file is verified by its own bytes — and nothing downstream
        # gates on it.
        quote = ""
        for pkg in swept.values():
            for sentence in (pkg.get("notes") or "").replace("\n", " ").split("."):
                low = _norm(sentence)
                if "mrc" in low and "isq" in low and "diffuse" in low:
                    quote = sentence.strip()
                    break
            if quote:
                break

        out.update(measured=True, slug=slug, n_orgs=len(orgs), n_catalogue=n_catalogue,
                   n_swept=len(swept), n_isq=n_isq, n_match=len(matches),
                   matches=sorted(m["title"] for m in matches), quote=quote)

        f_orgs = Fact.derived(str(len(orgs)), "organizations in the live CKAN organization_list")
        f_cat = Fact.derived(str(n_catalogue), "packages in the live CKAN catalogue "
                                               "(package_search rows=0 count)")
        f_swept = Fact.derived(str(len(swept)), "distinct CKAN packages enumerated and swept "
                                                "by this run")
        if quote:
            Fact.cited("ISQ's own diffusion geographies, per a live CKAN package's notes",
                       f"donneesquebec.ca package notes: \"{quote}\"")

        note += [
            f"- `organization_list` -> **{f_orgs}** organizations. The ISQ slug is RESOLVED "
            f"from that live list by the title predicate `{CKAN_ORG_TITLE_MARK!r}`: "
            + (f"**`{slug}`** (title match)." if slug else
               "**NO organization matched the predicate this run** — so no org-scoped sweep "
               "ran, and the swept population below is the term query alone."),
            f"- `package_search?rows=0` -> **{f_cat}** packages in the catalogue "
            f"(`{_count_str(total)}` reported).",
            f"- Swept: **{f_swept}** distinct packages — {n_isq} from "
            + (f"`organization:{slug}`" if slug else "no org-scoped query")
            + f" and the remainder from the live term query `{CKAN_TERM_SEARCH}`.",
            f"- Candidate predicate (the SAME two-tier predicate boundary B uses, applied to "
            f"title + notes + every resource name and url): an MRC term {list(MRC_TERMS)} AND "
            f"a projection term {list(PROJECTION_TERMS)} AND a population term "
            f"{list(POPULATION_TERMS)}. **{len(matches)}** of the {len(swept)} swept packages "
            f"matched"
            + (f": {sorted(m['title'] for m in matches)}." if matches else "."),
            "",
            # A FUNCTION of `matches`, not an unconditional sentence: with a match present,
            # calling this an absence would contradict the count one line above it — the
            # exact adjective-beside-a-correct-value defect this family keeps reintroducing.
            (f"  This boundary is therefore NOT an absence: {len(matches)} swept package(s) "
             f"matched the slug predicate. None of them is opened or body-checked here — "
             f"this boundary contributes the second searched population, and the verdict is "
             f"earned on boundary B below, where a candidate's bytes are actually inspected. "
             f"Whether a match is a real MRC-projection dataset or a slug-predicate false "
             f"positive is left to the reader: the titles are printed above, unglossed."
             if matches else
             f"  Scoped exactly: this is an absence **among the {len(swept)} packages this "
             f"run enumerated out of a {n_catalogue}-package catalogue** — not a claim about "
             f"the catalogue as a whole, and not a claim that ISQ publishes no MRC data. The "
             f"verdict is earned on boundary B below; this boundary contributes the second "
             f"searched population a NOT-FOUND would have to be scoped to."),
            "",
        ]
        if quote:
            note += [
                f"- CITED, verbatim from a live package's own `notes` (resolved by predicate, "
                f"not typed): *\"{quote}.\"* This is a statement about ISQ's publication "
                f"practice quoted from CKAN — it is NOT evidence about the file opened in §3, "
                f"which is verified by its own bytes, and nothing in the verdict rests on it.",
                "",
            ]
        return out
    except Exception as exc:
        out["why"] = f"{type(exc).__name__}: {exc}"
        note += [
            f"- `CKAN SWEEP NOT MEASURED THIS RUN: {out['why']}`",
            "",
            "  The CKAN boundary did not answer usefully. This does NOT demote a "
            "body-verified find on boundary B — a located source is located — but it DOES "
            "block a NOT-FOUND: with only one searched population swept, an absence claim "
            "would be scoped to a catalogue this run never enumerated. `_guard_not_found` "
            "enforces exactly that, and the run would record UNKNOWN-PROBE-FAILED instead.",
            "",
        ]
        return out


# --- the live hunt ------------------------------------------------------------------
def _hunt(note: list[str], stage: dict) -> tuple[str, dict]:
    """Run the live two-boundary hunt, append its record to `note`, return
    (verdict, evidence). `stage["at"]` tracks the current boundary so a raise can be
    attributed. Any raise is handled by main() -> UNKNOWN-PROBE-FAILED.
    """
    # ============ boundary A: the CKAN catalogue (searched population #2) ============
    stage["at"] = "ckan"
    ckan = _sweep_ckan(note)

    # ============ boundary B1: the ISQ sitemap (searched population #1) ==============
    stage["at"] = "isq-sitemap"
    xml = _sitemap()
    locs = _locs(xml)
    _guard_sitemap(xml, locs)  # RAISES (isq-sitemap)

    xlsx = [u for u in locs if u.lower().endswith(".xlsx")]
    # DEDUPED BY FILE, not by url: the sitemap publishes `/fr/fichier/<slug>` and
    # `/en/fichier/<slug>` as separate locs pointing at the SAME workbook. Counting both
    # would double every candidate figure below and print visibly duplicated table rows,
    # inflating the population the verdict is scoped over with files that do not exist.
    # The surviving url prefers PREFERRED_LANG_PATH — a DECLARED preference, not an
    # arbitrary sort artifact: the ISQ workbooks demoflow already pins are `/fr/` urls, so a
    # v1 extension pinning the url this note publishes stays on the repo's own convention.
    by_slug: dict[str, str] = {}
    for url in sorted(xlsx):
        if _terms(url, MRC_TERMS) and _terms(url, POPULATION_TERMS):
            slug = _slug(url)
            if slug not in by_slug or (PREFERRED_LANG_PATH in url
                                       and PREFERRED_LANG_PATH not in by_slug[slug]):
                by_slug[slug] = url
    swept = sorted(by_slug.values(), key=_slug)
    n_swept_urls = sum(1 for u in xlsx if _terms(u, MRC_TERMS) and _terms(u, POPULATION_TERMS))
    eligible = [u for u in swept if _terms(u, PROJECTION_TERMS)]

    f_locs = Fact.derived(str(len(locs)), "distinct <loc> entries in the live ISQ sitemap.xml")
    f_xlsx = Fact.derived(str(len(xlsx)), "of those locs that are .xlsx download urls")
    f_swept = Fact.derived(str(len(swept)), "swept: distinct .xlsx FILES (deduped by slug "
                                            "across language paths) naming an MRC term AND a "
                                            "population term")
    f_elig = Fact.derived(str(len(eligible)), "of the swept that ALSO name a projection term "
                                              "(pick-eligible)")

    note += [
        "## 2. Boundary B — ISQ's own product pages / full-edition downloads",
        "",
        f"- `{ISQ_SITEMAP}` -> **{f_locs}** distinct `<loc>` entries (deduped: the raw "
        f"document repeats each url once per hreflang alternate, so an un-deduped count would "
        f"overstate the population every absence claim below is scoped to), of which "
        f"**{f_xlsx}** are `.xlsx` download urls.",
        f"- Sweep predicate over the url slug (case-insensitive substring): an MRC term "
        f"{list(MRC_TERMS)} AND a population term {list(POPULATION_TERMS)} makes a url SWEPT; "
        f"a projection term {list(PROJECTION_TERMS)} additionally makes it ELIGIBLE (spec §8's "
        f"junction consumes projected population by scenario, so an estimates workbook is a "
        f"different product). **{f_swept}** swept, **{f_elig}** eligible — every absence claim "
        f"is therefore scoped to the WIDER swept set.",
        f"- The swept count is DEDUPED BY FILE: {n_swept_urls} matching locs collapse to "
        f"{len(swept)} distinct slugs, because the sitemap lists `/fr/fichier/<slug>` and "
        f"`/en/fichier/<slug>` separately for the same workbook.",
        "",
    ]

    # ============ boundary B2: observe every eligible candidate =====================
    stage["at"] = "isq-file"
    observed: dict[str, dict] = {u: _probe_url(u) for u in eligible}
    verified = sorted(u for u in eligible if _is_workbook_response(observed[u]))

    note += [
        f"**Every eligible candidate, observed live by GET** (status, content-type, declared "
        f"length and the first {PREFIX_BYTES} bytes — only a prefix is read, so a 17MB "
        f"candidate costs a handshake rather than a download). A bare 200 is NOT treated as "
        f"evidence: the magic-byte column is what separates a workbook from an HTML page "
        f"served at 200.",
        "",
        "| candidate (slug) | HTTP | content-type | Content-Length | magic bytes | "
        "workbook prefix? |",
        "|---|---:|---|---:|---|---|",
    ]
    for url in sorted(eligible):
        o = observed[url]
        note.append(
            f"| `{_slug(url)}` | {o['status']} | {o['ctype'] or '?'} | {o['length'] or '?'} "
            f"| `{o['prefix'].hex() or 'none'}` "
            f"| {'YES' if o['prefix'].startswith(XLSX_MAGIC) else 'no'} |"
        )
    note += [
        "",
        f"- **{len(verified)}** of the {len(eligible)} eligible candidates answered 200 with a "
        f"workbook magic-byte prefix. Note the exact scope of that number: it is a "
        f"STATUS-AND-PREFIX result, not a body-shape result"
        # Conditioned on `verified`: §3 exists only when a candidate survives to be opened.
        # Written unconditionally, this sentence promised a section that a NOT-FOUND or an
        # UNKNOWN run never writes — a forward reference to evidence that is not in the file.
        + (" — exactly ONE candidate is opened and shape-checked in §3, and only that one "
           "carries the three evidence pieces a LOCATED requires."
           if verified else
           ". NO candidate survived this screen, so this run opens NOTHING and there is no "
           "body-shape section below: no resource here carries the three evidence pieces a "
           "LOCATED requires."),
        "",
        f"**The plan body's two GUESSED slugs, probed live by this run** (so the comparison in "
        f"§4 is measured here rather than recalled):",
        "",
        "| guessed slug | HTTP (GET) |",
        "|---|---:|",
    ]
    guessed = {u: _probe_url(u, nbytes=0) for u in PLAN_GUESSED_SLUGS}
    for url in PLAN_GUESSED_SLUGS:
        note.append(f"| `{_slug(url)}` | {guessed[url]['status']} |")
    note.append("")

    if not verified:
        # An earned NOT-FOUND: both populations were swept and non-empty, and the ISQ sweep
        # resolved NO eligible candidate at all. The guard refuses every other shape —
        # notably candidates that exist but do not serve a workbook body.
        _guard_not_found(locs, eligible, verified, ckan)  # RAISES (isq-file) if unearned
        note += [
            f"- **The sweep resolved no eligible MRC-projection candidate.** Scoped exactly: "
            f"not among the {len(locs)} sitemap locs ({len(swept)} swept, {len(eligible)} "
            f"eligible) and the {ckan['n_swept']} CKAN packages swept from a "
            f"{ckan['n_catalogue']}-package catalogue. This is NOT a claim that no MRC-level "
            f"ISQ source exists.",
            "",
        ]
        return "NOT-FOUND", {
            "ckan": ckan, "n_locs": len(locs), "n_xlsx": len(xlsx), "n_swept": len(swept),
            "n_eligible": len(eligible), "n_verified": 0, "eligible": sorted(eligible),
            "guessed": {u: guessed[u]["status"] for u in PLAN_GUESSED_SLUGS},
        }

    # ============ §3 the body-shape check on ONE candidate ==========================
    # SELECTION RULE, stated before its result so it cannot drift to fit the answer:
    #   1. restrict to verified candidates matching a DECLARED demoflow family
    #      (`DEMOFLOW_RMR_FAMILY`) — the MRC analogue of a file demoflow already consumes at
    #      RMR level is what a v1 extension would read, so the witness must be one of those
    #      rather than merely the cheapest workbook on the site. This makes the family map
    #      LOAD-BEARING rather than a decorative table in §3;
    #   2. among those, the smallest by declared Content-Length (a shape witness only has to
    #      be sufficient; a 17MB download buys no extra evidence), ties broken by url;
    #   3. if NO verified candidate matches a family, fall back to the smallest verified
    #      overall — and say so in the note, because the witness is then weaker evidence
    #      about what a v1 extension could consume.
    def _declared_len(url: str) -> int:
        raw = observed[url]["length"]
        return int(raw) if str(raw).isdigit() else 1 << 62

    def _family_of(url: str) -> str:
        for family, terms in DEMOFLOW_RMR_FAMILY.items():
            if all(t in _norm(url) for t in terms):
                return family
        return ""

    family_verified = [u for u in verified if _family_of(u)]
    picked = sorted(family_verified or verified, key=lambda u: (_declared_len(u), u))[0]
    picked_family = _family_of(picked)
    # The METHOD comparison, MEASURED on the same url rather than asserted. The plan body's
    # hunt is HEAD-only; whether that is fatal on this host is an empirical question, and
    # the sentence emitted below is a function of these two observed codes.
    head = _probe_url(picked, method="HEAD", nbytes=0)
    head_disagrees = head["status"] != observed[picked]["status"]
    data = _download(picked)
    sheets, rows = _workbook_rows(data)
    header_row, header_col = _find_header(rows)
    labels = _labels(rows, header_row, header_col) if header_row is not None else []
    _guard_body(picked, observed[picked], sheets, header_row, header_col, labels)  # RAISES

    # The scenario axis, located by its OWN header cell — never by assuming column 0. An
    # earlier version read column 0 unconditionally and would have published this edition's
    # `Code` column as a list of "scenario labels": a fabricated axis with real-looking
    # values in it.
    scen_col, scen_head = _find_column(
        rows, header_row, lambda t: any(k in t for k in SCENARIO_HEADER_MARKS))
    scenarios = _labels(rows, header_row, scen_col) if scen_col >= 0 else []
    caption = str(rows[0][0]).strip() if rows and rows[0] and rows[0][0] else ""
    diffusion = _first_cell_matching(rows, "diffusion", max_rows=HEADER_SCAN_ROWS)
    if caption:
        Fact.cited("the opened workbook's own caption",
                   f"cell A1 of {_slug(picked)}: \"{caption}\"")
    if diffusion:
        Fact.cited("the opened workbook's own release line",
                   f"{_slug(picked)}: \"{diffusion}\"")

    # The per-target couronne search — the measurement that BEARS on the conclusion. The
    # count that matters is NOT "how many MRC labels exist" (105 labels would be equally
    # consistent with the couronne being absent); it is whether each DECLARED target is
    # among them, searched by name.
    found: dict[str, list[str]] = {}
    for ra, targets in COURONNE_MRC_BY_RA.items():
        for target in targets:
            found[target] = [m for m in labels if _norm(m) == _norm(target)]
    n_targets = sum(len(t) for t in COURONNE_MRC_BY_RA.values())
    hits = sorted(t for t, m in found.items() if m)
    misses = sorted(t for t, m in found.items() if not m)
    couronne_complete = not misses

    # Does the opened sheet carry an administrative-region axis at all? SEARCHED FOR, because
    # the RA↔MRC correspondence is the one thing spec §8's `ra_proxy` rows turn on: its
    # presence AND its absence both have to be measured to be stated. Editions differ — the
    # A2021 components sheet heads this column `RA1`; the 2025 sheets publish none.
    header_cells = [str(v).strip() for v in rows[header_row] if v is not None and str(v).strip()]
    ra_col, ra_head = _find_column(
        rows, header_row,
        lambda t: bool(RA_HEADER_PATTERN.match(t)) or any(k in t for k in RA_HEADER_MARKS))

    # The DECLARED RA number of each target, checked against the code the LIVE response puts
    # beside that MRC — an independent witness this file does not control (P5b's
    # declared-province pattern). Per target: the observed codes, and whether they agree.
    # `None` where the edition publishes no RA column: NOT CHECKABLE, never a silent pass.
    ra_observed: dict[str, list[str]] = {}
    ra_agrees: dict[str, bool | None] = {}
    for ra_key, targets in COURONNE_MRC_BY_RA.items():
        want = _declared_ra_number(ra_key)
        for target in targets:
            if ra_col < 0 or not found[target]:
                ra_observed[target], ra_agrees[target] = [], None
                continue
            codes = sorted({
                str(row[ra_col]).strip()
                for row in rows[header_row + 1:]
                if header_col < len(row) and ra_col < len(row)
                and row[header_col] is not None and row[ra_col] is not None
                and _norm(row[header_col]) == _norm(target) and str(row[ra_col]).strip()
            })
            ra_observed[target] = codes
            ra_agrees[target] = (bool(codes) and all(c == want for c in codes)) if want else None
    ra_checked = [t for t in ra_agrees if ra_agrees[t] is not None]
    ra_disagree = sorted(t for t in ra_checked if ra_agrees[t] is False)

    # The DECOMPOSITION, not the raw total: the column interleaves administrative-region
    # subtotal rows with the MRC rows, so "122 labels" would read as an MRC count and be
    # wrong by 17. What the non-aggregate remainder contains is NOT asserted — the full list
    # is emitted above and the reader judges it.
    aggregate_labels = [m for m in labels if AGGREGATE_LABEL_PATTERN.match(m)]
    fine_labels = [m for m in labels if not AGGREGATE_LABEL_PATTERN.match(m)]

    f_nlabels = Fact.derived(str(len(labels)), "distinct geography labels in the opened "
                                               "workbook's MRC column")
    f_ndecomp = Fact.derived(
        f"{len(aggregate_labels)} + {len(fine_labels)}",
        f"of those labels, the count in the `NN  Name` administrative-region-subtotal form "
        f"and the remainder")
    f_hits = Fact.derived(f"{len(hits)} of {n_targets}",
                          "declared couronne MRC targets found by exact name search of the "
                          "opened workbook's own labels")
    f_scen = Fact.derived(str(len(scenarios)),
                          f"distinct labels in the opened workbook's scenario column"
                          + (f" (header {scen_head!r})" if scen_col >= 0
                             else " — no column in its header row names a scenario axis"))
    f_ra = Fact.derived(
        f"{len(ra_checked) - len(ra_disagree)} of {len(ra_checked)}",
        "declared couronne targets whose DECLARED RA number equals the administrative-region "
        "code the opened workbook puts beside that MRC"
        + (f" (column {ra_col}, header {ra_head!r})" if ra_col >= 0
           else " — this edition publishes no RA column, so NONE was checkable"))

    note += [
        f"## 3. Body-shape check — is `{_slug(picked)}` really MRC-level?",
        "",
        f"- Selected DETERMINISTICALLY from the {len(verified)} verified candidates by the "
        f"rule stated in the code before its result: "
        + (f"{len(family_verified)} of them match a DECLARED demoflow family, and this is the "
           f"smallest of those by declared `Content-Length` ({observed[picked]['length']} "
           f"bytes) — family **{picked_family}**."
           if picked_family else
           f"NONE of them matches a declared demoflow family, so this is the fallback — the "
           f"smallest verified candidate overall ({observed[picked]['length']} bytes). The "
           f"witness is therefore weaker evidence about what a v1 extension could consume, "
           f"and this note says so rather than implying a family match.")
        + " A shape witness only has to be sufficient; the note does NOT claim this is the "
          "newest edition — the caption and release line below are read from its own bytes "
          "and state which edition it is.",
        f"- Full GET -> {len(data)} bytes; prefix `{observed[picked]['prefix'].hex()}` matches "
        f"the `{XLSX_MAGIC.hex()}` workbook magic; opened with {len(sheets)} sheet(s): "
        f"{sheets}.",
        f"- **Method comparison, measured on this same url:** GET -> "
        f"**{observed[picked]['status']}**, HEAD -> **{head['status']}**"
        + (f". The two DISAGREE, so on this host a HEAD-only hunt (which is what the plan "
           f"body's P6 sketch performs) would record this live workbook as absent. That is a "
           f"measured property of this endpoint, not a general rule."
           if head_disagrees else
           ". The two AGREE on this url, so this run records no HEAD/GET discrepancy here — "
           "the note draws no conclusion about HEAD-based hunts from it."),
        f"- Caption cell A1 (verbatim): *\"{caption}\"*" if caption
        else "- Cell A1 carries no caption this run.",
        f"- Release line (verbatim, resolved by predicate): *\"{diffusion}\"*" if diffusion
        else "- No cell in the header block names a diffusion date this run.",
        f"- Geography column located by a header cell BEGINNING `{MRC_HEADER_PREFIX.upper()}` "
        f"at row {header_row}, column {header_col} (0-indexed); the cell reads "
        f"`{header_cells[header_col] if header_col < len(header_cells) else '?'}`. Prefix, not "
        f"equality and not substring — measured reason: equality misses the 2016-2041 edition "
        f"(whose header reads \"MRC par région administrative\") and a substring test locks "
        f"onto the caption row, which also contains \"mrc\", and counts zero labels below it.",
        f"- Full header row (verbatim): {header_cells}.",
        f"- **{f_nlabels} distinct geography labels** below that header, which decompose as "
        f"**{f_ndecomp}**: labels in the `NN  Name` administrative-region-SUBTOTAL form, plus "
        f"the remainder. That split is emitted because the raw total would read as an MRC "
        f"count and be wrong — this column interleaves RA subtotals with the MRC rows. What "
        f"the remainder contains is NOT asserted here; the full list is emitted verbatim from "
        f"the live response, so the LEVEL is self-evidencing rather than glossed — a count "
        f"alone would leave \"MRC-level\" a word beside a number (P5b's precedent):",
        "",
    ]
    note += [f"  {i}. {label}" for i, label in enumerate(labels, start=1)]
    note += [
        "",
        f"- Scenario axis: "
        + (f"**{f_scen}** distinct labels in column {scen_col} (header `{scen_head}`): "
           f"{scenarios}."
           if scen_col >= 0 else
           f"**{f_scen}** — no cell in this sheet's header row names a scenario axis. The "
           f"sheet-name list above is emitted verbatim; this note draws no conclusion from it "
           f"about how this edition separates its scenarios."),
        "",
        f"**The declared couronne targets, searched BY NAME in those labels — {f_hits} found.** "
        f"The label COUNT above does not bear on couronne precision (a large MRC set is "
        f"equally consistent with the couronne being absent); this per-target search is the "
        f"measurement that does.",
        "",
        "| declared RA (spec §8 `ra_proxy`) | declared MRC target | found in the opened "
        "workbook? | RA code observed beside it | agrees with the declared RA number? |",
        "|---|---|---|---|---|",
    ]
    for ra_key, targets in COURONNE_MRC_BY_RA.items():
        want = _declared_ra_number(ra_key)
        for target in targets:
            agree = ra_agrees[target]
            note.append(
                f"| {ra_key} | {target} | "
                f"{'YES — ' + repr(found[target][0]) if found[target] else '**NO**'} | "
                f"{ra_observed[target] or '—'} | "
                + ("CORROBORATED" if agree is True
                   else f"**NOT CORROBORATED (declared {want})**" if agree is False
                   else "NOT CHECKABLE") + " |"
            )
    note += [
        "",
        f"- The target list is **DECLARED in this file** from spec §8's three `ra_proxy` rows, "
        f"not derived from the response; what is COMPUTED is the search result per target, and "
        f"a miss is published as a miss "
        + ("(none missed this run)." if couronne_complete
           else f"— MISSING this run: {misses}."),
        f"- **The RA↔MRC correspondence — {f_ra} declared targets corroborated.** "
        + (f"This edition DOES publish an administrative-region column (column {ra_col}, header "
           f"`{ra_head}`), so the RA number this file DECLARES for each target is checked "
           f"against the code the live response puts beside that MRC — an independent witness "
           f"nothing here controls. Flip a declared key to the wrong RA and the check stops "
           f"corroborating."
           + (f" **{len(ra_disagree)} target(s) DISAGREE: {ra_disagree} — treat every RA "
              f"grouping in this note as UNSUPPORTED until reconciled.**" if ra_disagree
              else "")
           if ra_col >= 0 else
           "This edition publishes NO administrative-region column — its header row is listed "
           "verbatim above — so NO target was checkable here and this run corroborates no RA "
           "grouping at all.")
        + " Membership is what this establishes; it is NOT a partition. This run does not "
          "compute whether these MRCs EXHAUST RA14/15/16, nor whether they exactly compose the "
          "Montréal RMR's couronne — a v1 Geography-enum extension needs both, and they remain "
          "open. Scoped to the ONE workbook opened here: nothing is claimed about the RA column "
          "of the other candidates in the §2 table, which were not opened.",
        "",
        f"- **Which swept files would feed a v1 extension.** demoflow consumes two ISQ families "
        f"at RMR level; the DECLARED term map {({k: list(v) for k, v in DEMOFLOW_RMR_FAMILY.items()})} "
        f"is matched against the ELIGIBLE slugs above (a slug match, not a schema comparison — "
        f"no equivalence between the RMR and MRC editions is tested here):",
        "",
    ]
    for family, terms in DEMOFLOW_RMR_FAMILY.items():
        fam = sorted(_slug(u) for u in eligible if all(t in _norm(u) for t in terms))
        note.append(f"  - **{family}** -> {len(fam)} eligible slug(s) match: {fam or 'none'}")
    note.append("")

    evidence = {
        "ckan": ckan,
        "n_locs": len(locs), "n_xlsx": len(xlsx), "n_swept": len(swept),
        "n_eligible": len(eligible), "n_verified": len(verified),
        "eligible": sorted(eligible), "verified": verified,
        "url": picked, "status": observed[picked]["status"],
        "head_status": head["status"], "head_disagrees": head_disagrees,
        "ctype": observed[picked]["ctype"], "length": observed[picked]["length"],
        "nbytes": len(data), "sheets": sheets, "header_row": header_row,
        "header_col": header_col, "labels": labels, "n_labels": len(labels),
        "n_aggregate": len(aggregate_labels), "n_fine": len(fine_labels),
        "scenarios": scenarios, "scen_col": scen_col, "scen_head": scen_head,
        "caption": caption, "diffusion": diffusion, "family": picked_family,
        "hits": hits, "misses": misses, "n_targets": n_targets,
        "couronne_complete": couronne_complete,
        "ra_col": ra_col, "ra_head": ra_head, "ra_observed": ra_observed,
        "n_ra_checked": len(ra_checked), "ra_disagree": ra_disagree,
        "guessed": {u: guessed[u]["status"] for u in PLAN_GUESSED_SLUGS},
    }
    return "LOCATED", evidence


def _guessed_str(evidence: dict) -> str:
    """The plan's guessed slugs and the status each ANSWERED, for the §4 comparison.

    Module-level, not inline in `main()`: `test_probe_contracts.py` locates the note
    assembly by SHAPE (the first `<sep>.join(...)` in `main()`), so a second join anywhere
    above it hides the real one from the contract gate. Keeping helper joins out of `main()`
    keeps that gate pointed at the assembly it exists to check.
    """
    return ", ".join(
        f"`{_slug(url)}` -> HTTP {status}"
        for url, status in (evidence.get("guessed") or {}).items()
    ) or "not probed this run"


def main() -> None:
    # Per-run registry (see run_p3.py): `_wds` is one cached module shared by every probe,
    # so a module-global list would let one run's figures inflate another's.
    facts = new_run()
    title = ["# P6 — MRC-level ISQ source hunt (RECORDED OBSERVATION)", ""]
    body: list[str] = []
    stage = {"at": "ckan"}

    verdict = "UNKNOWN-PROBE-FAILED"
    evidence: dict = {}
    try:
        verdict, evidence = _hunt(body, stage)
    except Exception as exc:  # outage, a vacuous 200, or a wrong-body page — never a false verdict
        boundary = stage.get("at", "ckan")
        host = "donneesquebec.ca" if boundary == "ckan" else ISQ_HOST
        body += [
            "## LIVE HUNT VERDICT: UNKNOWN-PROBE-FAILED",
            "",
            f"- `LIVE PROBE FAILED-AT: {boundary}` (host: {host})",
            f"- `LIVE PROBE FAILED: {type(exc).__name__}: {exc}`",
            "",
            "  The hunt did not answer usefully at the boundary named above — an outage, or a "
            "200 carrying an empty/wrong body, or a searched population too thin to earn an "
            "absence (all caught by the floor guard). This run therefore records neither a "
            "located source NOR a not-found: an unearned NOT-FOUND would be the cheap all-clear "
            "this gate exists to refuse. Re-run against live sources to record the hunt.",
            "",
        ]

    body += ["## 4. DECISION", ""]
    guessed_str = _guessed_str(evidence)

    if verdict == "LOCATED":
        e = evidence
        ck = e["ckan"]
        scope = (f"the {e['n_locs']} ISQ sitemap locs swept in §2 ({e['n_swept']} matched the "
                 f"MRC×population predicate, {e['n_eligible']} eligible)")
        if ck["measured"]:
            scope += (f" and the {ck['n_swept']} CKAN packages swept in §1 from a "
                      f"{ck['n_catalogue']}-package catalogue")
        else:
            scope += " (the CKAN boundary was NOT MEASURED this run — see §1)"
        # Every clause below is a FUNCTION of a computed value, so a gloss cannot contradict
        # the number it sits beside.
        couronne = (f"{len(e['hits'])} of {e['n_targets']} declared couronne MRC targets found "
                    f"by exact name search")
        couronne += (" — ALL declared targets present" if e["couronne_complete"]
                     else f" — MISSING: {e['misses']}")
        body += [
            "- `DECISION-VERDICT: LOCATED`",
            f"- `DECISION-RESOURCE-URL: {e['url']}`",
            f"- `DECISION-HTTP-STATUS: {e['status']} ({e['ctype'] or 'no content-type'}, "
            f"Content-Length {e['length'] or 'unreported'})`  (observed by GET this run; the "
            f"same url answered HTTP {e['head_status']} to HEAD"
            + (" — the methods DISAGREE here, so a HEAD-only hunt would miss this file)"
               if e["head_disagrees"] else " — the methods agree here)"),
            f"- `DECISION-BODY-SHAPE: {e['nbytes']} bytes downloaded, magic-byte prefix "
            f"matches {XLSX_MAGIC.hex()}, opened to sheets {e['sheets']}, MRC header cell at "
            f"row {e['header_row']} column {e['header_col']}, {e['n_labels']} distinct "
            f"geography labels, "
            + (f"{len(e['scenarios'])} scenario labels {e['scenarios']}"
               if e["scen_col"] >= 0 else "no scenario column in this sheet")
            + "`",
            # NO backticks inside the token value: `_probe_asserts.token` parses the
            # backtick-delimited span non-greedily, so an inner backtick truncates the value
            # and the gate would read a decomposition as a bare number.
            f"- `DECISION-MRC-LABEL-COUNT: {e['n_labels']} ({e['n_aggregate']} of them in the "
            f"NN-Name administrative-region-subtotal form + {e['n_fine']} others)`  "
            f"(distinct labels below the MRC-named header of the opened workbook. Precisely: "
            f"the header NAMES an MRC axis and this count says that column is populated. It "
            f"is NOT an MRC count — the column interleaves RA subtotals, hence the split; the "
            f"full label list is emitted verbatim in §3. And it says NOTHING about the "
            f"couronne — a large label set is equally consistent with the couronne being "
            f"absent — which is why the per-target search below is a separate token)",
            f"- `DECISION-COURONNE-TARGETS: {couronne}`",
            f"- `DECISION-RA-CORRESPONDENCE: "
            + (f"{e['n_ra_checked'] - len(e['ra_disagree'])} of {e['n_ra_checked']} declared "
               f"targets corroborated against the opened workbook's own RA column "
               f"(column {e['ra_col']}, header {e['ra_head']!r})"
               + (f"; DISAGREEING: {e['ra_disagree']}" if e["ra_disagree"] else "")
               if e["ra_col"] >= 0 else
               "NOT CHECKABLE — the opened workbook publishes no administrative-region column")
            + "`  (MEMBERSHIP only. This run does NOT compute whether these MRCs partition "
            "RA14/15/16 or exactly compose the Montréal RMR's couronne — a v1 Geography-enum "
            "extension needs both and they remain open)",
            f"- `DECISION-SWEPT-POPULATION: {scope}`",
            f"- `DECISION-SPEC-PREMISE: CONTRADICTED — ESCALATION`  (spec §8 records "
            f"\"no MRC workbook exists — probed 404, 2026-07-21\". MEASURED THIS RUN: the "
            f"plan's guessed slugs {guessed_str}, while the resource above answers "
            f"{e['status']} with a body this run opened and shape-checked. The two together "
            f"say the 404 was a property of the GUESSED SLUG CONVENTION, not of the data. This "
            f"note does NOT edit the spec — the contradiction is escalated, per envelope.)",
            "",
            "- **Standing rule (spec §11.6): v0 PROCEEDS REGARDLESS.** A find enables a **v1** "
            "`Geography` enum extension for couronne-nord precision — never a v0 change. In v0 "
            "the RA14/15/16 rows keep their `ra_proxy` flag (spec §8): they remain ranking "
            "members, never balance participants, never emitted in `ScenarioPrior`. Nothing in "
            "this note licenses a v0 loader change.",
            "",
        ]
    elif verdict == "NOT-FOUND":
        e = evidence
        ck = e["ckan"]
        body += [
            "- `DECISION-VERDICT: NOT-FOUND`",
            f"- `DECISION-SWEPT-POPULATION: the {e['n_locs']} ISQ sitemap locs swept in §2 "
            f"({e['n_swept']} matched the MRC×population predicate, {e['n_eligible']} eligible, "
            f"{e['n_verified']} verified) and the {ck['n_swept']} CKAN packages swept in §1 "
            f"from a {ck['n_catalogue']}-package catalogue`",
            "- `DECISION-NOT-FOUND-SCOPE: an absence AMONG THE POPULATIONS NAMED ABOVE — this "
            "run does NOT claim that no MRC-level ISQ source exists`",
            f"- `DECISION-SPEC-PREMISE: NOT CONTRADICTED BY THIS RUN`  (spec §8's \"no MRC "
            f"workbook exists\" stands unchallenged by this sweep; the plan's guessed slugs "
            f"answered {guessed_str})",
            "",
            "- **Standing rule (spec §11.6): v0 PROCEEDS REGARDLESS.** A find enables a **v1** "
            "`Geography` enum extension for couronne-nord precision — never a v0 change. In v0 "
            "the RA14/15/16 rows keep their `ra_proxy` flag (spec §8): they remain ranking "
            "members, never balance participants, never emitted in `ScenarioPrior`. Nothing in "
            "this note licenses a v0 loader change.",
            "",
        ]
    else:
        body += [
            f"- `DECISION-VERDICT: {verdict}`",
            "- No MRC-level source was located this run AND no absence was earned (see the "
            "boundary failure above). The searched population was too thin, or a boundary "
            "answered with a body that cannot support a verdict — either way this is a "
            "recorded observation, not an invented find and not a hollow not-found.",
            "",
            "- **Standing rule (spec §11.6): v0 PROCEEDS REGARDLESS.** A find enables a **v1** "
            "`Geography` enum extension for couronne-nord precision — never a v0 change. In v0 "
            "the RA14/15/16 rows keep their `ra_proxy` flag (spec §8): they remain ranking "
            "members, never balance participants, never emitted in `ScenarioPrior`. Nothing in "
            "this note licenses a v0 loader change.",
            "",
        ]

    header = provenance_header(facts, written_by=_WRITTEN_BY, scope=_SCOPE,
                               summary=_summary, cited_label=_CITED_LABEL)
    text = "\n".join(title + header + body) + "\n"
    for placeholder in ("[FILL:", "[FILL]", "[FILL "):
        if placeholder in text:
            raise AssertionError(f"run_p6.py emitted an unresolved {placeholder!r} placeholder")
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
