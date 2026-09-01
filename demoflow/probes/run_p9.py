"""P9 — close the SEARCH class: an exhaustive MEMBER-LEVEL sweep of the StatCan cube catalogue.

Writes `probes/P9-catalogue-closure.md` and the committed derived index
`demoflow/data/catalogue_member_index_p9.json`. This module is the only writer of both.

WHY THIS PROBE EXISTS. Three absence claims in this arc were refuted by a cube the search
could not see, never by the data:

  * ruling F — the search used HEAD against a host whose HEAD 404s on a path whose GET is 200,
    over guessed slugs;
  * ruling Q — the search was scoped to one product family and a title tier, which hid
    43-10-0060-01;
  * ruling S — the search selected on DIMENSION NAMES, which hid 98-10-0621-01, a cube that
    carries immigrant status as MEMBERS of a `Population characteristics (46)` dimension.

Each fix was narrower than the failure. This probe ends the class by NOT SELECTING AT ALL:
every cube in the catalogue is resolved, and both vocabularies are matched against dimension
names AND every member name of every dimension. What remains after that is a VOCABULARY
residual, not a scope residual — and the vocabularies are printed in the note so a reader can
judge them rather than take the closure on trust.

WHAT IS MEASURED, exactly:

    catalogue     = getAllCubesListLite                 (every productId StatCan publishes)
    metadata      = getCubeMetadata for EVERY one       (no title/family/dimension filter)
    match(cube)   = for each vocabulary V in {IMMIGRANT, HOUSEHOLD}:
                      dimension-level hit  iff any term of V is a substring of any
                                               normalized dimensionNameEn
                      member-level hit     iff any term of V is a substring of any
                                               normalized memberNameEn of any dimension
    FLAGGED class = both vocabularies hit AND at least one of them is MEMBER-ONLY
                    (member-level hit with no dimension-level hit for that same vocabulary)

The FLAGGED class is the point: 43-10-0060-01 and 98-10-0621-01 both fall in it, and it is
exactly the class a dimension-name search cannot see.

NORMALIZATION, stated because it is part of the match rule and therefore part of the verdict:
NBSP -> space, whitespace runs collapsed, casefolded. The NBSP leg is not hypothetical —
43-10-0060-01's geography labels carry trailing NBSPs (`'Montréal (CMA), Que.\\xa0\\xa0'`)
while 98-10-0621-01's do not.

THE RAW PULL IS NOT COMMITTED, and the anchor pattern is T13b/DIV-F2's. The full metadata pull
is **5.29 GB** across 8,226 cubes — MEASURED by `stat()` on the 2026-08-14 pull, and recorded
here because the first draft of this docstring ESTIMATED it at ~400 MB, which the same run's own
measurement contradicted by a factor of thirteen. That is the depth-1 defect class this arc
grades, so the fix is not a better literal: `sweep()` reads the size off the cache into
`cache_bytes`, `build_index` publishes it as `raw_pull_bytes`, and the note prints THAT. This
paragraph is the one place a human-readable size still appears in prose, and it is a measurement
with a date rather than an estimate. 5.29 GB is far past what belongs in this repo, so what is
committed is the COMPACT DERIVED INDEX, and the pull itself is pinned by digest in
`pins.RAW_SOURCE_SHA256`, exactly as the P2 extract pins its 850 MB upstream member (which the
raw pull outweighs six times over). The digest is taken over a CANONICAL re-serialization
(sorted keys, compact separators, catalogue first, then one metadata response per line in
productId order), not over the bytes off the wire: batch boundaries and key order are not
stable across pulls, the canonical form is, and it is what a re-pull must reproduce.

EVERY HEADER FIELD IS A FUNCTION OF THE CACHE, never of the clock. The pull writes a
`manifest.json` recording its own date and wall clock; the derivation reads it. A `date.today()`
anywhere in the derivation would break the regen-equality gate on the second day of the
artifact's life while looking perfectly correct on the first.

THE FLOOR GUARDS (each raises `ProbeRefusal`, which routes the run to UNKNOWN-PROBE-FAILED —
never to a friendlier verdict; the name is deliberately NOT network-class so a refusal cannot
launder itself into `pytest.skip`):

  * `_guard_catalogue`   — the catalogue is non-empty, its productIds are unique, and it
                           CONTAINS both positive-control cubes. A truncated or empty list
                           would otherwise publish a closure over a catalogue of nothing.
  * `_guard_complete`    — the resolved pid set equals the catalogue pid set EXACTLY and every
                           response is SUCCESS with at least one dimension. A closure claim over
                           a gappy pull is the very failure this probe exists to end, so a gap
                           refuses rather than being footnoted.
  * `_guard_scan`        — the scan actually read members: members scanned > dimensions scanned
                           > 0. A member-level claim over zero members read is vacuous.
  * `_guard_positive_control` — 98100621 AND 43100060 both land in the FLAGGED class. This is
                           the falsifiable part: a sweep that cannot re-find the two cubes whose
                           misses motivated it has not closed anything, whatever it counted.

Run (timing and size MEASURED on the 2026-08-14 pull, not estimated — each run publishes its
own from the cache manifest and `stat()` rather than from these two lines):
    cd demoflow && uv run python probes/run_p9.py --pull  --cache DIR   # 1,211 s -> 5.29 GB
    cd demoflow && uv run python probes/run_p9.py --cache DIR           # derive; no re-pull
"""
import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from _wds import (
    WDS_LIST,
    WDS_META,
    WDS_TIMEOUT,
    Fact,
    new_run,
    post,
    provenance_header,
    table_number,
)

from demoflow.loaders.pins import DATA_DIR, verify_raw_anchor

_WRITTEN_BY = Path(__file__).name
_SCOPE = (
    "Every figure below is COMPUTED by that run from the cached full-catalogue pull it names "
    "— the catalogue count, every match count, every listed cube and the pull digest alike. "
    "Nothing here is a remembered result: the closure claim is only as good as the pull it "
    "is derived from, and that pull is pinned by digest so the claim can be re-checked."
)
_CITED_LABEL = "Externally cited figures (published elsewhere, not computed here):"

OUT = Path(__file__).resolve().parent / "P9-catalogue-closure.md"
_TITLE = "# P9 — full-catalogue MEMBER-LEVEL closure sweep (StatCan WDS)"

# The committed derived index, and the name under which its (uncommittable) upstream pull is
# pinned. Both keys live in `pins`; see the registry block there for why the raw anchor is a
# separate registry from the committed-file one.
INDEX_ARTIFACT = "catalogue_member_index_p9.json"

# ---------------------------------------------------------------------------
# THE VOCABULARIES. These ARE the residual: a cube whose relevant axis is worded outside
# these lists is not closed by this sweep, which is why they are published verbatim in the
# note. Kept exactly as the mandate states them, including the nestings ("migrant" is a
# substring of "immigrant"; "permanent resident" of "non-permanent resident"; "household
# maintainer" of "primary household maintainer") — a term that always co-fires is harmless,
# while silently pruning one would narrow the recorded vocabulary away from the stated one.
# ---------------------------------------------------------------------------
IMMIGRANT_TERMS = (
    "immigrant", "immigration", "generation status", "admission category",
    "period of immigration", "place of birth", "citizenship", "landed",
    "permanent resident", "non-permanent resident", "newcomer", "birthplace", "migrant",
)
HOUSEHOLD_TERMS = (
    "household maintainer", "primary household maintainer", "tenure", "owner", "renter",
    "dwelling", "housing", "household size", "persons per household", "household type",
    "shelter",
)
VOCABULARIES = {"immigrant": IMMIGRANT_TERMS, "household": HOUSEHOLD_TERMS}

# The DIRECT fork-class test's household half: the maintainer axis carried as a DIMENSION.
# A member of HOUSEHOLD_TERMS by construction — `maintainer_cross` reads the terms the scan
# already matched rather than re-matching, so this cannot silently name a term the sweep does
# not search for.
MAINTAINER_DIMENSION_TERM = "household maintainer"

# StatCan geoLevel codes for census metropolitan areas and CMA parts (measured live
# 2026-08-14 on 98100621: 503 carries "St. John's (CMA), N.L.", 504 carries the CAs; on
# 43100060: 505 carries "Ottawa–Gatineau (Quebec part) (CMA), Ontario/Quebec"). The name
# markers are a UNION with the code rule, not a fallback: a cube that reaches CMA under
# either rule reaches CMA, and relying on the code alone would be one more selection rule
# of exactly the kind this probe exists to stop.
CMA_GEO_LEVELS = frozenset({503, 505})
CMA_NAME_MARKERS = ("(cma)", "(rmr)")

# The positive control. These are the two cubes whose misses produced rulings Q and S; both
# sit in the FLAGGED class, so a sweep that does not re-find them has not closed anything.
POSITIVE_CONTROL = (98100621, 43100060)

_BATCH = 60
_PULL_RETRIES = 6
_UNATTRIBUTED = "unattributed"


class ProbeRefusal(RuntimeError):
    """A floor guard fired: this run may NOT publish a closure verdict.

    Deliberately not a network-class exception name — `tests/_probe_asserts.py`'s
    NETWORK_EXCEPTIONS decides fail-vs-skip, and a refusal that could be mistaken for an
    outage would launder the cardinal cheap all-clear into a green-looking skip.
    """

    def __init__(self, boundary: str, message: str) -> None:
        super().__init__(message)
        self.boundary = boundary


# ---------------------------------------------------------------------------
# Normalization + matching
# ---------------------------------------------------------------------------
def normalize(name: object) -> str:
    """NBSP -> space, whitespace runs collapsed, casefolded.

    Part of the match rule, therefore part of the verdict, therefore stated in the note.
    `casefold` rather than `lower` so that a name arriving in an unexpected case form still
    matches the ASCII vocabularies.
    """
    return " ".join(str(name).replace("\xa0", " ").split()).casefold()


def matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    """Vocabulary terms occurring as substrings of an ALREADY-normalized name."""
    return [t for t in terms if t in text]


def _geo_dimension_positions(dimensions: list) -> list[int]:
    """Positions of every dimension carrying geography, detected STRUCTURALLY.

    By `geoLevel` on members, never by the dimension being named "Geography": a name test is
    the same class of selection rule that hid 98-10-0621-01. Returns every such dimension —
    a cube with two geography axes must not have one of them silently dropped.
    """
    return [
        d.get("dimensionPositionId")
        for d in dimensions
        if any(m.get("geoLevel") is not None for m in d.get("member") or [])
    ]


def _cma_reach(dimensions: list) -> tuple[bool, list[int]]:
    """(reaches CMA, the sorted geoLevel codes present), over the geography dimensions."""
    geo_positions = set(_geo_dimension_positions(dimensions))
    levels: set[int] = set()
    reach = False
    for dim in dimensions:
        if dim.get("dimensionPositionId") not in geo_positions:
            continue
        for member in dim.get("member") or []:
            level = member.get("geoLevel")
            if level is not None:
                levels.add(level)
            if level in CMA_GEO_LEVELS:
                reach = True
            elif any(mark in normalize(member.get("memberNameEn")) for mark in CMA_NAME_MARKERS):
                reach = True
    return reach, sorted(levels)


def scan_cube(obj: dict) -> dict:
    """Match both vocabularies against one cube's dimension names AND every member name.

    Returns the per-cube record the index is built from. Pure: no network, no clock.
    """
    dimensions = obj.get("dimension") or []
    result = {
        "pid": product_id(obj),
        "title": obj.get("cubeTitleEn"),
        "n_dimensions": len(dimensions),
        "n_members": sum(len(d.get("member") or []) for d in dimensions),
        "archived": obj.get("archiveStatusCode"),
        "vocab": {},
    }
    for vocab, terms in VOCABULARIES.items():
        dim_hits: dict[str, list[str]] = {}
        member_hits: dict[str, list[str]] = {}
        for dim in dimensions:
            dim_name = dim.get("dimensionNameEn")
            hits = matched_terms(normalize(dim_name), terms)
            if hits:
                dim_hits[str(dim_name)] = hits
            for member in dim.get("member") or []:
                member_name = member.get("memberNameEn")
                hits = matched_terms(normalize(member_name), terms)
                if hits:
                    member_hits.setdefault(str(dim_name), [])
                    if str(member_name) not in member_hits[str(dim_name)]:
                        member_hits[str(dim_name)].append(str(member_name))
        if dim_hits and member_hits:
            level = "both"
        elif dim_hits:
            level = "dimension"
        elif member_hits:
            level = "member-only"
        else:
            level = "none"
        result["vocab"][vocab] = {
            "level": level,
            "dimension_matches": dim_hits,
            "member_matches": {k: sorted(v) for k, v in member_hits.items()},
        }
    reach, levels = _cma_reach(dimensions)
    result["cma_reach"] = reach
    result["geo_levels"] = levels
    return result


def classify(record: dict) -> str:
    """`flagged` | `both-dimension-level` | `single-vocabulary` | `none`.

    `flagged` = BOTH vocabularies hit and at least ONE of them member-only. That is the class
    both missed cubes fall into and the class no dimension-name search can see.
    """
    levels = {v: record["vocab"][v]["level"] for v in VOCABULARIES}
    if any(level == "none" for level in levels.values()):
        return "none" if all(level == "none" for level in levels.values()) else "single-vocabulary"
    return "flagged" if "member-only" in levels.values() else "both-dimension-level"


def maintainer_cross(record: dict) -> bool:
    """Does this cube carry a `household maintainer` DIMENSION together with ANY immigrant term?

    The DIRECT fork-class test, and a narrower question than the FLAGGED class: it asks for the
    exact cross rulings S and T are built on — the maintainer axis as a dimension of its own,
    with immigrant vocabulary present anywhere (dimension OR member, which is the whole point,
    since 98-10-0621-01 carries it only in members).

    Recorded, never guarded. The class counts and the positive control are invariants of the
    METHOD and refuse when they break; this is a property of a VINTAGE — a later catalogue may
    legitimately publish a fifth such cube, and a floor guard here would turn StatCan releasing
    data into a probe failure. So it is measured, published and left falsifiable.
    """
    named = any(MAINTAINER_DIMENSION_TERM in terms
                for terms in record["vocab"]["household"]["dimension_matches"].values())
    return named and record["vocab"]["immigrant"]["level"] != "none"


def human_bytes(n: int) -> str:
    """`n` as a decimal-prefixed size (GB = 10^9) — the unit `du`/`ls` report and the one the
    5.29 GB figure in this module's docstring is stated in. Unit chosen from the value so the
    same code reads correctly for the multi-GB real pull and the sub-MB test fixture."""
    for unit, scale in (("GB", 10 ** 9), ("MB", 10 ** 6), ("kB", 10 ** 3)):
        if n >= scale:
            return f"{n / scale:.2f} {unit}"
    return f"{n} B"


# ---------------------------------------------------------------------------
# Cache: pull, canonical serialization, digest
# ---------------------------------------------------------------------------
def product_id(body: dict) -> int:
    """The productId of a `getCubeMetadata` response object, as an INT.

    MEASURED 2026-08-14, and load-bearing: `getAllCubesListLite` types productId as an
    integer (`10100001`) while `getCubeMetadata` types the SAME id as a string
    (`'10100001'`). Comparing the two raw makes every set operation between the catalogue and
    the pull vacuously disjoint — which in this probe means the completeness guard reports
    100% of the catalogue unresolved AND 100% of the pull extraneous (it did, on the first
    full run), and in the PULL loop means every single pid reads as missing from its own batch
    and gets re-requested one at a time. Normalizing at the boundary, once, is what keeps both
    from being tuned away as false alarms.
    """
    return int(body["productId"])


def _canonical(obj: object) -> str:
    """One canonical JSON line. Sorted keys + compact separators + no ASCII escaping.

    The digest is taken over THIS form, not over the response bytes: batch boundaries and key
    order are not stable across pulls, so hashing the wire bytes would report drift on every
    re-pull and therefore anchor nothing.
    """
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _fetch_with_retry(pids: list[int]) -> list:
    """POST one metadata batch, with a bounded retry on transport-class failures.

    `_wds.post` deliberately has NO retry — that is load-bearing there, because a probe must
    be able to tell "the catalogue lacks this cube" from "the service did not answer". The
    retry lives HERE, at the pull, where 138 consecutive batches make a single transient
    failure otherwise fatal to a 1,211 s (~20 min, measured 2026-08-14) run. It cannot soften
    any verdict: a pid that never resolves is not defaulted, it is left ABSENT, and
    `_guard_complete` then refuses the whole run. Retry is a throughput measure; completeness
    is still proved, never assumed.
    """
    last: Exception | None = None
    for attempt in range(_PULL_RETRIES):
        try:
            return post(WDS_META, [{"productId": p} for p in pids])
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            last = exc
            time.sleep(3 * (attempt + 1))
    raise ProbeRefusal("wds-meta", f"batch of {len(pids)} failed {_PULL_RETRIES}x: {last!r}")


def pull(cache: Path) -> None:
    """Fill `cache` with catalogue.json, meta.jsonl and manifest.json. 1,211 s -> 5.29 GB.

    Both figures are MEASURED (2026-08-14 pull) rather than estimated, and neither is what any
    artifact reads: the wall clock lands in the manifest this function writes, and the size is
    `stat()`-ed by `sweep()`, so a run whose pull differs publishes ITS numbers, not these.

    Writes the manifest LAST and only on a complete pull, so a half-filled cache cannot be
    mistaken for a finished one: the derivation refuses a cache with no manifest.
    """
    cache.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    t0 = time.time()
    catalogue = json.loads(urllib.request.urlopen(WDS_LIST, timeout=WDS_TIMEOUT).read())
    (cache / "catalogue.json").write_text(_canonical(catalogue), encoding="utf-8")
    pids = sorted({c["productId"] for c in catalogue})
    print(f"catalogue: {len(catalogue)} rows / {len(pids)} unique pids", flush=True)

    retries = 0
    unresolved: list[int] = []
    with (cache / "meta.jsonl").open("w", encoding="utf-8") as fh:
        for i in range(0, len(pids), _BATCH):
            chunk = pids[i:i + _BATCH]
            resp = _fetch_with_retry(chunk)
            # Responses are keyed by their OWN productId, never by request order, and a
            # non-SUCCESS element may not carry one at all — so a failed pid inside a batch is
            # UNATTRIBUTABLE. Re-request those singly, where attribution is unambiguous.
            got = {product_id(o["object"]) for o in resp
                   if o.get("status") == "SUCCESS" and isinstance(o.get("object"), dict)}
            for obj in resp:
                fh.write(_canonical(obj) + "\n")
            for pid in chunk:
                if pid in got:
                    continue
                retries += 1
                single = _fetch_with_retry([pid])
                if single and single[0].get("status") == "SUCCESS":
                    fh.write(_canonical(single[0]) + "\n")
                else:
                    unresolved.append(pid)
            if (i // _BATCH) % 20 == 0:
                print(f"  {i + len(chunk)}/{len(pids)}  {time.time() - t0:.0f}s", flush=True)

    elapsed = time.time() - t0
    (cache / "manifest.json").write_text(_canonical({
        "pulled_at": started.date().isoformat(),
        "pull_started_utc": started.isoformat(timespec="seconds"),
        "wall_clock_seconds": round(elapsed, 1),
        "batch_size": _BATCH,
        "single_pid_refetches": retries,
        "unresolved_product_ids": sorted(unresolved),
        "catalogue_rows": len(catalogue),
        "endpoint_list": WDS_LIST,
        "endpoint_meta": WDS_META,
    }), encoding="utf-8")
    print(f"pull complete in {elapsed:.0f}s; {retries} single-pid refetches; "
          f"{len(unresolved)} unresolved", flush=True)


def read_manifest(cache: Path) -> dict:
    path = cache / "manifest.json"
    if not path.exists():
        raise ProbeRefusal(
            "cache",
            f"{path} is missing — the manifest is written only by a COMPLETE pull, so its "
            "absence means the cache is partial. Every date and timing field in the artifact "
            "header comes from it; reading the clock instead would make the artifact "
            "un-regenerable on any later day.",
        )
    return json.loads(path.read_text(encoding="utf-8"))


def index_cache(cache: Path) -> dict[int, int]:
    """productId -> byte offset of its line in meta.jsonl.

    Offsets rather than a pid->object dict: the pull is 5.29 GB of JSON (measured), which as
    live Python objects does not fit a sane resident set — the single largest cube alone is
    268 MB. The derivation seeks, parses one cube, derives its record and drops it.
    """
    offsets: dict[int, int] = {}
    path = cache / "meta.jsonl"
    with path.open("rb") as fh:
        offset = 0
        for line in fh:
            length = len(line)
            stripped = line.strip()
            if stripped:
                obj = json.loads(stripped)
                body = obj.get("object")
                pid = (product_id(body) if isinstance(body, dict) and body.get("productId")
                       is not None else None)
                if pid is None:
                    raise ProbeRefusal(
                        "cache",
                        f"a cached response at byte {offset} carries no object.productId "
                        f"(status={obj.get('status')!r}) — it cannot be attributed to a cube, "
                        "and an unattributable response in a closure sweep is a gap.",
                    )
                if pid in offsets:
                    raise ProbeRefusal(
                        "cache",
                        f"productId {pid} appears twice in {path} — a resumed or appended "
                        "cache can double-write, and a duplicated cube would be counted twice "
                        "in every total this note publishes.",
                    )
                offsets[pid] = offset
            offset += length
    return offsets


def read_cube(cache: Path, offset: int) -> dict:
    with (cache / "meta.jsonl").open("rb") as fh:
        fh.seek(offset)
        return json.loads(fh.readline().decode("utf-8"))


# ---------------------------------------------------------------------------
# Floor guards
# ---------------------------------------------------------------------------
def _guard_catalogue(catalogue: list) -> list[int]:
    if not catalogue:
        raise ProbeRefusal("wds-list", "getAllCubesListLite returned an EMPTY catalogue — a "
                                       "closure over nothing is the vacuous-success failure.")
    pids = [c["productId"] for c in catalogue]
    if len(set(pids)) != len(pids):
        raise ProbeRefusal("wds-list", f"the catalogue repeats product ids "
                                       f"({len(pids)} rows, {len(set(pids))} unique)")
    missing = [p for p in POSITIVE_CONTROL if p not in set(pids)]
    if missing:
        raise ProbeRefusal(
            "wds-list",
            f"the catalogue does not contain the positive-control cube(s) {missing} — a "
            "truncated catalogue would otherwise publish a closure over a partial universe.",
        )
    return sorted(pids)


def _guard_complete(catalogue_pids: list[int], resolved: dict[int, int], statuses: dict) -> None:
    missing = sorted(set(catalogue_pids) - set(resolved))
    extra = sorted(set(resolved) - set(catalogue_pids))
    if missing or extra:
        raise ProbeRefusal(
            "cache",
            f"the pull does not cover the catalogue exactly: {len(missing)} catalogue cube(s) "
            f"unresolved (first: {missing[:5]}), {len(extra)} resolved cube(s) not in the "
            "catalogue. A closure claim over a gappy pull is precisely the absence-by-search "
            "failure this probe exists to end.",
        )
    bad = {pid: st for pid, st in statuses.items() if st != "SUCCESS"}
    if bad:
        raise ProbeRefusal(
            "cache",
            f"{len(bad)} cube(s) answered with a non-SUCCESS status (first: "
            f"{sorted(bad.items())[:5]}) — an unread cube is an unsearched cube.",
        )


def _guard_scan(n_dimensions: int, n_members: int, no_dimension: list[int]) -> None:
    if n_dimensions <= 0 or n_members <= n_dimensions:
        raise ProbeRefusal(
            "scan",
            f"the scan read {n_members} members across {n_dimensions} dimensions — a "
            "MEMBER-level closure claim over a scan that read no members is vacuous.",
        )
    if no_dimension:
        raise ProbeRefusal(
            "scan",
            f"{len(no_dimension)} cube(s) resolved with NO dimension list (first: "
            f"{no_dimension[:5]}) — they were counted as scanned but nothing in them was read.",
        )


def _guard_positive_control(classes: dict[int, str]) -> None:
    wrong = {pid: classes.get(pid) for pid in POSITIVE_CONTROL if classes.get(pid) != "flagged"}
    if wrong:
        raise ProbeRefusal(
            "scan",
            f"the positive control failed: {wrong} — 98100621 and 43100060 are the two cubes "
            "whose misses produced rulings Q and S, and both sit in the FLAGGED class by "
            "construction. A sweep that cannot re-find them has closed nothing, whatever "
            "totals it computed.",
        )


# ---------------------------------------------------------------------------
# The sweep + the committed index
# ---------------------------------------------------------------------------
def sweep(cache: Path) -> dict:
    """Derive everything from the cache: digest, per-cube records, counts. No clock, no network."""
    manifest = read_manifest(cache)
    catalogue = json.loads((cache / "catalogue.json").read_text(encoding="utf-8"))
    catalogue_pids = _guard_catalogue(catalogue)

    offsets = index_cache(cache)
    digest = hashlib.sha256()
    digest.update((_canonical(sorted(catalogue, key=lambda c: c["productId"])) + "\n").encode())

    statuses: dict[int, str] = {}
    classes: dict[int, str] = {}
    records: dict[int, dict] = {}
    cross: list[int] = []
    n_dimensions = n_members = 0
    no_dimension: list[int] = []
    for pid in sorted(offsets):
        obj = read_cube(cache, offsets[pid])
        digest.update((_canonical(obj) + "\n").encode())
        statuses[pid] = obj.get("status")
        body = obj["object"]
        if not (body.get("dimension") or []):
            no_dimension.append(pid)
        record = scan_cube(body)
        n_dimensions += record["n_dimensions"]
        n_members += record["n_members"]
        classes[pid] = classify(record)
        # Evaluated for EVERY cube, right here, before any retention rule can reach it. A cube
        # carrying a maintainer dimension and immigrant vocabulary is always retained under
        # today's rule — but that is a consequence of the rule, not of the question, and a
        # later narrowing of retention must not silently narrow this measurement with it.
        if maintainer_cross(record):
            cross.append(pid)
        # Full records are RETAINED only for the cubes the index lists. Keeping all 8,000+
        # (each carrying every matched member name) is a multi-GB resident set for data the
        # index never reads — the class is what the totals need, and the class is kept for
        # every cube.
        if classes[pid] in ("flagged", "both-dimension-level"):
            records[pid] = record

    _guard_complete(catalogue_pids, offsets, statuses)
    _guard_scan(n_dimensions, n_members, no_dimension)
    _guard_positive_control(classes)

    release_times = sorted(c["releaseTime"] for c in catalogue if c.get("releaseTime"))
    return {
        "manifest": manifest,
        "raw_sha256": digest.hexdigest(),
        # MEASURED off the cache, never estimated — this is the value the note publishes, and
        # the reason the ~400 MB literal that used to stand in this module's docstring can no
        # longer reach an artifact. `stat()` and not `time`-anything: the derivation is
        # clock-free by contract (see the AST gate in tests/test_probe_p9.py).
        "cache_bytes": sum((cache / name).stat().st_size
                           for name in ("catalogue.json", "meta.jsonl", "manifest.json")),
        "catalogue_count": len(catalogue),
        "resolved_count": len(offsets),
        "latest_release_time": release_times[-1] if release_times else None,
        "records": records,
        "classes": classes,
        "maintainer_cross": sorted(cross),
        "n_dimensions": n_dimensions,
        "n_members": n_members,
    }


def build_index(swept: dict) -> dict:
    """The COMPACT committed index. A pure function of `swept` — deterministic bytes.

    Enumerates every cube matching BOTH vocabularies (a superset of the FLAGGED class, so a
    reader can re-derive the flagged subset from the file rather than trust this run's
    partition), and counts the rest. Cubes matching one vocabulary or neither are counted but
    not listed: enumerating them would be most of the catalogue, and a 5.29 GB copy of the pull
    (measured 2026-08-14) is not an index — the same sentence this function's own note emits,
    where the size is interpolated from `raw_pull_bytes` rather than typed.
    """
    classes = swept["classes"]
    records = swept["records"]
    listed = sorted(pid for pid, klass in classes.items()
                    if klass in ("flagged", "both-dimension-level"))
    tally = {klass: sum(1 for k in classes.values() if k == klass)
             for klass in ("flagged", "both-dimension-level", "single-vocabulary", "none")}
    manifest = swept["manifest"]
    return {
        "_provenance": {
            "artifact": INDEX_ARTIFACT,
            "generated_by": f"probes/{_WRITTEN_BY}",
            "run_date": manifest["pulled_at"],
            "cube_list_vintage": {
                "pulled_at": manifest["pulled_at"],
                "pull_started_utc": manifest["pull_started_utc"],
                "catalogue_rows": swept["catalogue_count"],
                "latest_release_time_in_catalogue": swept["latest_release_time"],
            },
            "raw_pull_sha256": swept["raw_sha256"],
            "raw_pull_bytes": swept["cache_bytes"],
            "raw_pull_canonical_form": (
                "sha256 over: canonical JSON of the catalogue array sorted by productId, "
                "newline, then one canonical getCubeMetadata response per line in ascending "
                "productId order (json.dumps sort_keys=True, ensure_ascii=False, separators "
                "(',',':')), each newline-terminated, UTF-8"
            ),
            "endpoints": {"catalogue": manifest["endpoint_list"],
                          "metadata": manifest["endpoint_meta"]},
            "vocabularies": {"immigrant": list(IMMIGRANT_TERMS),
                             "household": list(HOUSEHOLD_TERMS)},
            "normalization": "NBSP->space, whitespace runs collapsed, casefold; English names only",
            "cma_rule": {"geo_levels": sorted(CMA_GEO_LEVELS),
                         "name_markers": list(CMA_NAME_MARKERS)},
            "scanned": {"cubes": swept["resolved_count"], "dimensions": swept["n_dimensions"],
                        "members": swept["n_members"]},
            "class_counts": tally,
            "maintainer_cross": {
                "rule": (
                    f"cubes carrying a dimension whose name matches {MAINTAINER_DIMENSION_TERM!r} "
                    "together with any immigrant-vocabulary match at dimension OR member level"
                ),
                "product_ids": swept["maintainer_cross"],
            },
            "listing_rule": (
                "every cube matching BOTH vocabularies is listed; single-vocabulary and "
                "non-matching cubes are counted in class_counts only"
            ),
        },
        "cubes": [
            {
                "pid": pid,
                "table": table_number(pid),
                "title": records[pid]["title"],
                "class": classes[pid],
                "cma_reach": records[pid]["cma_reach"],
                "geo_levels": records[pid]["geo_levels"],
                "immigrant": records[pid]["vocab"]["immigrant"],
                "household": records[pid]["vocab"]["household"],
            }
            for pid in listed
        ],
    }


def write_index(payload: dict) -> tuple[Path, str]:
    """Write the committed index deterministically and return (path, its own sha256)."""
    path = DATA_DIR / INDEX_ARTIFACT
    body = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    path.write_text(body, encoding="utf-8")
    return path, hashlib.sha256(body.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# The note
# ---------------------------------------------------------------------------
def _summary(*, total: int, derived: int, cited: int) -> str:
    return (f"This run registered {total} provenance-tagged figures: {derived} DERIVED from "
            f"the cached pull and {cited} CITED from sources outside it.")


def _terms_line(terms: tuple[str, ...]) -> str:
    return ", ".join(f"`{t}`" for t in terms)


def _cell(title: object) -> str:
    """A live cube title as one markdown cell. Pipes are escaped — an unescaped one would
    silently split the row into extra columns and misalign every value after it."""
    return str(title).replace("|", "\\|")


def _cube_row(entry: dict) -> str:
    """One row of the FLAGGED-and-reaches-CMA table."""
    imm, hh = entry["immigrant"], entry["household"]
    return (f"| {entry['table']} | {_cell(entry['title'])} | {imm['level']} | {hh['level']} | "
            f"{'yes' if entry['cma_reach'] else 'no'} |")


def _cross_row(entry: dict) -> str:
    """One row of the direct maintainer-cross table (no household column: every row in it
    carries the maintainer dimension by construction, so printing it would be a constant)."""
    return (f"| {entry['table']} | {_cell(entry['title'])} | {entry['immigrant']['level']} | "
            f"{'yes' if entry['cma_reach'] else 'no'} |")


def _sections(cache: Path, where: list) -> list:
    where[0] = "cache"
    swept = sweep(cache)
    # THE PIN GATE, before a single artifact byte is written (run_p2.py's precedent). The
    # digest is printed first so the DELIBERATE first pin / re-pin has the value it needs:
    # `verify_raw_anchor` raises without it, and a pin transcribed from a raised message is
    # not a pin taken from a measurement.
    where[0] = "pin"
    print(f"canonical raw pull sha256: {swept['raw_sha256']}", flush=True)
    verify_raw_anchor(swept["raw_sha256"], INDEX_ARTIFACT)
    payload = build_index(swept)
    where[0] = "artifact"
    index_path, index_sha = write_index(payload)
    prov = payload["_provenance"]
    tally = prov["class_counts"]

    catalogue_fact = Fact.derived(swept["catalogue_count"],
                                  "len(getAllCubesListLite) from the cached pull")
    resolved_fact = Fact.derived(swept["resolved_count"],
                                 "cubes with a SUCCESS getCubeMetadata response in the cache")
    dims_fact = Fact.derived(f"{swept['n_dimensions']:,}", "dimensions read across all cubes")
    members_fact = Fact.derived(f"{swept['n_members']:,}", "member names read across all cubes")
    sha_fact = Fact.derived(swept["raw_sha256"], "sha256 over the canonical full pull")
    index_sha_fact = Fact.derived(index_sha, f"sha256 of the emitted {INDEX_ARTIFACT}")
    flagged_fact = Fact.derived(tally["flagged"],
                                "cubes matching BOTH vocabularies with >=1 vocabulary member-only")
    both_dim_fact = Fact.derived(tally["both-dimension-level"],
                                 "cubes matching BOTH vocabularies, both at dimension level")
    single_fact = Fact.derived(tally["single-vocabulary"], "cubes matching exactly one vocabulary")
    none_fact = Fact.derived(tally["none"], "cubes matching neither vocabulary")
    wall_fact = Fact.derived(f"{swept['manifest']['wall_clock_seconds']:.0f}",
                             "wall-clock seconds of the pull, recorded in the cache manifest")
    listed = payload["cubes"]
    flagged_entries = [e for e in listed if e["class"] == "flagged"]
    flagged_cma = [e for e in flagged_entries if e["cma_reach"]]
    flagged_cma_fact = Fact.derived(len(flagged_cma),
                                    "FLAGGED cubes whose geography dimension reaches CMA")
    control_tables = ", ".join(table_number(p) for p in POSITIVE_CONTROL)
    size_fact = Fact.derived(
        human_bytes(swept["cache_bytes"]),
        "stat() over the cache's catalogue.json + meta.jsonl + manifest.json")
    cross_pids = prov["maintainer_cross"]["product_ids"]
    cross_fact = Fact.derived(
        len(cross_pids),
        f"cubes carrying a {MAINTAINER_DIMENSION_TERM!r} DIMENSION with any immigrant term")
    cross_tables_fact = Fact.derived(
        ", ".join(table_number(p) for p in cross_pids),
        "the product ids of that cross, in ascending order")
    by_pid = {e["pid"]: e for e in listed}

    lines = [
        "## Decision block",
        "",
        "- `DECISION-VERDICT: CLOSED-AT-MEMBER-LEVEL`",
        f"- `DECISION-CLOSURE-LEVEL: dimension names AND every member name, all {catalogue_fact} "
        f"catalogue cubes`",
        f"- `DECISION-CATALOGUE-COUNT: {catalogue_fact}`",
        f"- `DECISION-RESOLVED-COUNT: {resolved_fact}`",
        f"- `DECISION-CUBE-LIST-VINTAGE: pulled {prov['run_date']}, latest releaseTime in "
        f"catalogue {swept['latest_release_time']}`",
        f"- `DECISION-RAW-PULL-SHA256: {sha_fact}`",
        f"- `DECISION-INDEX-ARTIFACT: demoflow/data/{INDEX_ARTIFACT} sha256 {index_sha_fact}`",
        f"- `DECISION-FLAGGED-COUNT: {flagged_fact}`",
        f"- `DECISION-MAINTAINER-CROSS: {cross_fact} cubes — {cross_tables_fact}`",
        f"- `DECISION-POSITIVE-CONTROL: {control_tables} both FLAGGED`",
        "- `DECISION-RESIDUAL: vocabulary-scoped; English member/dimension names only; "
        "StatCan WDS only`",
        "",
        "## 1. What was scanned, and why the whole catalogue",
        "",
        "Three absence claims in this arc were refuted by a cube the SEARCH could not see:",
        "ruling F (HEAD against a host whose HEAD 404s on a GET-200 path, over guessed slugs),",
        "ruling Q (a product-family + title-tier scope, which hid 43-10-0060-01) and ruling S",
        "(selection on dimension NAMES, which hid 98-10-0621-01 — a cube carrying immigrant",
        "status as MEMBERS of a `Population characteristics (46)` dimension). Each fix was",
        "narrower than the failure, so this sweep does not select at all.",
        "",
        f"- Catalogue: **{catalogue_fact}** cubes from `getAllCubesListLite`.",
        f"- Metadata resolved: **{resolved_fact}** cubes via `getCubeMetadata`, with NO title,",
        "  family, subject or dimension pre-filter.",
        f"- Read: **{dims_fact}** dimension names and **{members_fact}** member names.",
        f"- Pull wall clock: **{wall_fact}s**, batch size {_BATCH}.",
        f"- Raw pull sha256 (canonical form): `{sha_fact}`.",
        "",
        f"The raw pull is **{size_fact}** on disk — measured by this run, not estimated — and is",
        "NOT committed. What is committed is the compact derived index",
        f"`demoflow/data/{INDEX_ARTIFACT}`, pinned in `pins.WORKBOOK_SHA256`, with the",
        "pull's digest pinned separately in `pins.RAW_SOURCE_SHA256` — the same DIV-F2 pattern",
        "the 850 MB P2 upstream member uses. The digest is taken over a CANONICAL",
        "re-serialization (catalogue first, then one response per line in productId order,",
        "sorted keys, compact separators), because wire bytes are not stable across batch",
        "boundaries and would anchor nothing.",
        "",
        "## 2. The match rule (this IS the verdict's scope)",
        "",
        "For each cube, each vocabulary is matched as a SUBSTRING against the normalized",
        "`dimensionNameEn` of every dimension AND the normalized `memberNameEn` of every member",
        "of every dimension. Normalization: NBSP -> space, whitespace runs collapsed, casefold.",
        "The NBSP leg is not hypothetical — 43-10-0060-01's geography labels carry trailing",
        "NBSPs while 98-10-0621-01's do not.",
        "",
        f"- IMMIGRANT-ish ({len(IMMIGRANT_TERMS)} terms): {_terms_line(IMMIGRANT_TERMS)}",
        f"- HOUSEHOLD-ish ({len(HOUSEHOLD_TERMS)} terms): {_terms_line(HOUSEHOLD_TERMS)}",
        "",
        "A vocabulary is **member-only** for a cube when it hits a member name and NO dimension",
        "name. The **FLAGGED** class is: both vocabularies hit, at least one of them member-only.",
        "That is the class 43-10-0060-01 and 98-10-0621-01 both fall into, and the class a",
        "dimension-name search structurally cannot see.",
        "",
        "Geography dimensions are detected STRUCTURALLY (any dimension with a member carrying a",
        "non-null `geoLevel`), never by the dimension being NAMED `Geography` — a name test is",
        "the same class of selection rule that hid 98-10-0621-01. CMA reach is the UNION of",
        f"`geoLevel` in {sorted(CMA_GEO_LEVELS)} and a member name containing",
        f"{' or '.join(repr(m) for m in CMA_NAME_MARKERS)}.",
        "",
        "## 3. What the sweep found",
        "",
        "| class | cubes |",
        "|---|---:|",
        f"| **FLAGGED** — both vocabularies, >=1 member-only | **{flagged_fact}** |",
        f"| both vocabularies, both at dimension level | {both_dim_fact} |",
        f"| exactly one vocabulary | {single_fact} |",
        f"| neither vocabulary | {none_fact} |",
        f"| catalogue total | {catalogue_fact} |",
        "",
        f"Of the {flagged_fact} FLAGGED cubes, **{flagged_cma_fact}** reach CMA geography.",
        "",
        "The FLAGGED class is deliberately OVER-inclusive — it is a sensitivity floor, not a",
        "shortlist. Read the titles in §3a: the `Canadian Business Counts` and",
        "`Access to public transport` rows match on NAICS- and transit-worded members, not on",
        "anything about immigrant households. That is the correct behaviour for an instrument",
        "whose job is to miss nothing; §3b is where the question is asked narrowly.",
        "",
        f"**POSITIVE CONTROL.** {control_tables} are the two cubes whose misses produced rulings",
        "Q and S. Both are re-found here in the FLAGGED class, by the floor guard rather than by",
        "inspection: a sweep that could not re-find them would refuse to publish a verdict at",
        "all, whatever totals it computed.",
        "",
        "### 3a. The FLAGGED cubes that reach CMA",
        "",
        "| table | title | immigrant match | household match | CMA |",
        "|---|---|---|---|---|",
    ]
    lines += ([_cube_row(e) for e in flagged_cma] or
              ["| _none_ | no FLAGGED cube reaches CMA geography in this pull | — | — | — |"])
    lines += [
        "",
        "The full listing — every cube matching BOTH vocabularies at any level, with the",
        "dimension and member names that matched — is the committed index",
        f"`demoflow/data/{INDEX_ARTIFACT}`. Single-vocabulary and non-matching cubes are counted",
        "in that file's `class_counts` and not enumerated: listing them would be most of the",
        f"catalogue, and a {size_fact} copy of the pull is not an index.",
        "",
        "### 3b. The DIRECT fork-class cross — a maintainer DIMENSION with immigrant vocabulary",
        "",
        f"Narrower than the FLAGGED class and asked directly: **exactly {cross_fact} cubes** in "
        f"the whole catalogue",
        f"carry a `{MAINTAINER_DIMENSION_TERM}` DIMENSION together with any immigrant-vocabulary",
        f"term at either level — {cross_tables_fact}.",
        # Worded as "no other cube carries the cross", NOT as "nothing else crosses them at
        # dimension level": the immigrant half of this cross is member-only in all four rows
        # above, so the shorter phrasing invites a reader to conclude the opposite of what the
        # table shows.
        "No other cube in the catalogue carries that maintainer dimension alongside immigrant",
        "vocabulary at any level at all.",
        "",
        "| table | title | immigrant match | CMA |",
        "|---|---|---|---|",
    ]
    # Subscripted, NOT `.get`-filtered: a cross cube matches both vocabularies by construction
    # and is therefore always listed, so a miss is a broken invariant. A filter would print
    # fewer rows than the count above claims and read as a shorter true answer.
    lines += ([_cross_row(by_pid[pid]) for pid in cross_pids] or
              ["| _none_ | no cube in this pull carries that cross | — | — |"])
    lines += [
        "",
        "Read against the rulings this arc already carries: 98-10-0621-01 is the CMA cube ruling",
        "S draws both immigrant inputs from; 98-10-0622-01 is its census-division/subdivision",
        "sibling, which ruling T measures RA06 and RA13 from; 98-10-0623-01 (CMA) and",
        "98-10-0624-01 (CD/CSD) carry the same cross in the shelter-cost family and are recorded",
        "as available CORROBORATION, not used by the module.",
        "",
        "This is a property of a VINTAGE, not an invariant of the method, so it is recorded and",
        "left falsifiable rather than made a floor guard: a later catalogue may legitimately",
        "publish a fifth such cube, and a guard here would turn a StatCan release into a probe",
        "failure. It moves with the pull digest above, which is what makes it re-checkable.",
        "",
        "## 4. The closure, stated at the level actually achieved",
        "",
        "**The search is closed at MEMBER level over the full StatCan WDS catalogue as of the",
        f"pull of {prov['run_date']} ({catalogue_fact} cubes, raw pull sha256 `{sha_fact}`).**",
        "Every cube's dimension names and every one of its member names were read and matched",
        "against both vocabularies. No cube was excluded by title, product family, subject,",
        "release date, archive status or dimension name.",
        "",
        "**What this does NOT close — named, not buried:**",
        "",
        "1. **Vocabulary.** A cube whose relevant axis is worded outside the two lists in §2 is",
        "   not reached by this sweep. The lists are printed above precisely so a reader can",
        "   judge them: e.g. an axis worded only as `country of origin`, `mother tongue`,",
        "   `visible minority`, `ethnic origin`, `occupancy`, `condominium` or `household",
        "   composition` carries no term from either list. This is a REAL residual and the",
        "   honest limit of a substring sweep.",
        "2. **Language.** Only `cubeTitleEn`, `dimensionNameEn` and `memberNameEn` were scanned.",
        "   A cube whose English naming differs from its French naming in a way that moves a",
        "   term out of the vocabulary is not reached.",
        "3. **Punctuation forms.** Matching is a plain substring test after NBSP and whitespace",
        "   normalization: a name spelling `non\\u2011permanent` with a non-breaking hyphen, or",
        "   hyphenating a multi-word term differently, is not reached.",
        "4. **Everything outside StatCan WDS.** ISQ, IRCC, CMHC, JLR, municipal rôle and every",
        "   other publisher are entirely outside this sweep's universe.",
        "",
        # Worded WITHOUT the forbidden phrase rather than around it. The gate in
        # tests/test_probe_p9.py is a plain substring check and cannot tell an assertion from
        # its own denial — and it is right not to try: a note that prints the unscoped-absence
        # sentence at all can be quoted out of it, and a disclaimer is a weaker instrument than
        # simply never making the claim. (Caught live by that gate on the first generated note,
        # whose disclaimer carried the phrase verbatim.)
        "This note therefore makes NO unscoped absence claim — it does not assert that nothing",
        "further exists. It says what was scanned, how, and what would still slip through —",
        "which is the standing consequence ruling S records: an absence claim in this arc is",
        "provisional until the search itself has been closed at the level the claim is stated",
        "at, and a scoped verdict must name its selection level, not merely its pool.",
        "",
        "## 5. Reproducing this",
        "",
        "```",
        f"cd demoflow && uv run python probes/{_WRITTEN_BY} --pull  --cache DIR   "
        f"# {wall_fact}s -> {size_fact}, as measured here",
        f"cd demoflow && uv run python probes/{_WRITTEN_BY} --cache DIR",
        "```",
        "",
        "The derivation is a pure function of the cache: every date and timing figure above is",
        "read from the cache's own `manifest.json`, never from the clock, so re-deriving from",
        "the same pull reproduces this file and the committed index BYTE-FOR-BYTE. A re-pull",
        "that yields a different digest is a new catalogue VINTAGE — re-pin",
        "`pins.RAW_SOURCE_SHA256` deliberately and regenerate both artifacts; the probe refuses",
        "to write against an unpinned or drifted pull.",
        "",
    ]
    return lines


def _failure_sections(exc: BaseException, where: list) -> list:
    """The UNKNOWN branch. Records the exception TYPE and the boundary it happened at."""
    boundary = getattr(exc, "boundary", where[0])
    return [
        "## Decision block",
        "",
        "- `DECISION-VERDICT: UNKNOWN-PROBE-FAILED`",
        f"- `LIVE PROBE FAILED: {type(exc).__name__}: {exc}`",
        f"- `LIVE PROBE FAILED-AT: {boundary}`",
        "",
        "## 1. What this run could not establish",
        "",
        "This probe closes an absence-claim class by scanning the WHOLE catalogue at MEMBER",
        "level. This run did not complete that scan, so it closes NOTHING: no closure level, no",
        "counts, no index. An unfinished sweep is not a narrower closure — it is no closure, and",
        "recording it as one would be the exact failure (an absence that is a property of the",
        "search) the probe exists to end.",
        "",
    ]


def _assert_no_placeholder(text: str) -> None:
    if "[FILL" in text:
        raise ProbeRefusal("note", "an unresolved [FILL placeholder survived into the note — "
                                   "every value must be COMPUTED, never invited")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", required=True, type=Path,
                        help="directory holding catalogue.json / meta.jsonl / manifest.json")
    parser.add_argument("--pull", action="store_true",
                        help="fetch the full catalogue + metadata into --cache first "
                             "(~20 min; 1,211 s -> 5.29 GB measured 2026-08-14)")
    args = parser.parse_args()

    log = new_run()
    where = [_UNATTRIBUTED]
    try:
        if args.pull:
            where[0] = "wds-list"
            pull(args.cache)
        sections = _sections(args.cache, where)
    except Exception as exc:                      # noqa: BLE001 — every failure is recorded
        sections = _failure_sections(exc, where)
    header = provenance_header(log, written_by=_WRITTEN_BY, scope=_SCOPE, summary=_summary,
                               cited_label=_CITED_LABEL)
    text = "\n".join([_TITLE, ""] + header + sections) + "\n"
    _assert_no_placeholder(text)
    OUT.write_text(text, encoding="utf-8")
    print("\n".join(line for line in sections if line.startswith("- `")))


if __name__ == "__main__":
    sys.exit(main())
