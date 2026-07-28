"""Shared WDS/HTTP core + provenance registry for probes/run_p3..p5.py.

Imported FLAT (`import _wds`), not as `probes._wds`: probes/ is deliberately NOT a
package, and in script mode `sys.path[0]` IS probes/, so the flat form resolves
natively. A package layout breaks `uv run python probes/run_p3.py` (demoflow/ is
never on sys.path there) — the live path this module must not disturb. The cost is
that a loader which does NOT put probes/ on sys.path (e.g.
`importlib.util.spec_from_file_location`, used by the p4/p5 test harnesses) must
insert it before `exec_module`; those two `_load_run_p*` helpers do exactly that.

RESIDUAL, stated plainly: `_ACTIVE` is not reset when a probe's `main()` returns, so
a `Fact` constructed AFTER a run appends to that run's now-stale log. This is
strictly no worse than the module-global list it replaces, and it can never reach
another run's note, because `provenance_header` reads only the log it is handed —
never a free variable. `provenance_header` deliberately does not "seal" the log, so
it stays a pure function of its argument and is safely re-callable.
"""

import contextvars
import json
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

# --- WDS endpoints ----------------------------------------------------------
WDS_META = "https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata"  # POST [{"productId": int}]
WDS_LIST = "https://www150.statcan.gc.ca/t1/wds/rest/getAllCubesListLite"
WDS_DATA = "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromCubePidCoordAndLatestNPeriods"
TIMEOUT = 120


# --- Fact provenance registry -----------------------------------------------
@dataclass
class FactLog:
    """One run's registry of provenance-tagged figures.

    Per-RUN, not per-module: this module is cached in `sys.modules`, so a module
    global would be shared by every probe and every fresh test load. Binding the log
    in `main()` makes cross-run contamination impossible by construction rather than
    by remembering to call `.clear()` first.
    """

    facts: list["Fact"] = field(default_factory=list)


_ACTIVE: contextvars.ContextVar["FactLog | None"] = contextvars.ContextVar(
    "_wds_active_factlog", default=None
)


def new_run() -> FactLog:
    """Start a fresh per-run registry and make it the active one. Returns it.

    A `ContextVar` rather than a plain global so two probe bodies interleaved on
    threads/tasks each see their own log instead of clobbering each other.
    """
    log = FactLog()
    _ACTIVE.set(log)
    return log


@dataclass(frozen=True)
class Fact:
    """A narrative figure, carrying HOW this run obtained it.

    Structural guard against a defect this probe family kept reintroducing: a
    hand-typed literal printed under prose asserting the run computed it. The facts
    AND the document's provenance header are both generated from these objects, so a
    figure cannot reach a note without declaring itself either

      `derived` — computed from a live response in THIS run (it changes when the
                  source data changes), naming the exact source, or
      `cited`   — external to this run, printed with its citation inline.

    The header is then assembled from the mix actually present rather than asserted,
    so it cannot drift from what the body really contains.

    Known weakness: `derived` does NOT verify the value was computed — the tag is
    author-chosen. So the discipline is enforced by CODE: every value tagged
    `derived` in the probes is a live expression over the fetched response, never a
    literal handed to `Fact.derived`.
    """

    text: str
    kind: str  # "derived" | "cited"
    source: str

    def __post_init__(self) -> None:
        log = _ACTIVE.get()
        if log is None:
            raise RuntimeError(
                "Fact created with no active run: call _wds.new_run() first. A registry "
                "that silently accepted it would let one run's figures inflate another "
                "run's provenance count — the exact defect this registry exists to stop."
            )
        log.facts.append(self)

    @classmethod
    def derived(cls, value: object, how: str) -> "Fact":
        return cls(f"{value}", "derived", how)

    @classmethod
    def cited(cls, value: object, source: str) -> "Fact":
        return cls(f"{value}", "cited", source)

    def __str__(self) -> str:
        return self.text if self.kind == "derived" else f"{self.text} [cited: {self.source}]"


def provenance_header(
    log: FactLog,
    *,
    written_by: str,
    scope: str,
    summary: Callable[..., str],
    cited_label: str,
) -> list[str]:
    """Describe a note's provenance from the facts it ACTUALLY contains.

    The skeleton is shared; 100% of the prose is per-probe, so every string is a
    parameter. Picking any one probe's wording as canonical would rewrite two other
    notes' provenance headers — the exact drift this registry exists to prevent,
    committed by the extraction itself.

    `log` is positional and required: the header reads only what it is handed, never
    a free variable, so a `main()` that forgot to open a run cannot publish a count
    borrowed from someone else's.

    `summary` is called KEYWORD-ONLY — `summary(total=, derived=, cited=)`. Positional
    `(total, derived, cited)` is a silent-corruption vector exactly at p3, whose counts
    are 8/8/0: swapping `total` and `derived` produces identical output there, so no
    test could catch it.
    """
    derived = [f for f in log.facts if f.kind == "derived"]
    cited = [f for f in log.facts if f.kind == "cited"]
    lines = [
        f"Written by `probes/{written_by}`; nothing in this file is hand-edited.",
        "",
        scope,
    ]
    if log.facts:
        lines.append(summary(total=len(log.facts), derived=len(derived), cited=len(cited)))
    if cited:
        lines += ["", cited_label]
        lines += [f"- {f.text} — {f.source}" for f in cited]
    lines.append("")
    return lines


# --- HTTP -------------------------------------------------------------------
def post(url: str, payload: list) -> list:
    """POST a JSON payload to a WDS endpoint and return the parsed response.

    Deliberately NO try/except, no HTTP-status check, no retry, no sentinel return.
    That is load-bearing, not an oversight: run_p3.py wraps individual
    `_post(WDS_META, …)` calls in its OWN try/except to distinguish "the catalogue
    genuinely lacks this cube" from "the service did not answer". A `post()` that
    caught `HTTPError`, retried, or returned `[]` would collapse that distinction and
    let a real outage publish a false NOT-FOUND.
    """
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    return json.loads(urllib.request.urlopen(req, timeout=TIMEOUT).read())


# --- StatCan table-number derivation ----------------------------------------
def table_number(pid: object) -> str:
    """`98100134` -> `98-10-0134-01`, StatCan's published table-number form.

    Derived, never typed: the note interpolates a dynamic `found_pid` beside this
    string, so a hardcoded table number would mislabel whichever cube actually
    won. (98100137 carries both required members and fails only the age
    predicate — had it won, a literal would have printed the wrong table.)

    The `raise` is not softened to a `str(pid)` fallback: that would let a malformed
    productId print into a committed note as if it were a valid StatCan table number
    — precisely the hand-written-claim failure this probe family forbids.
    """
    p = str(pid)
    if len(p) != 8 or not p.isdigit():
        raise ValueError(f"unexpected productId shape {pid!r}; cannot derive a table number")
    return f"{p[0:2]}-{p[2:4]}-{p[4:8]}-01"


def table_url(pid: object) -> str:
    """The public table URL for a product id (the `pid` query arg appends `01`)."""
    return f"https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid={pid}01"
