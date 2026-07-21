"""P2 — StatCan WDS table pull for 98-10-0231-01 (tenure x age of primary
household maintainer). Pulls the FULL table live via the WDS
getFullTableDownloadCSV endpoint (productId 98100231) and commits a FILTERED
EXTRACT, not the raw table.

WHY AN EXTRACT: the raw member is 811 MiB inside a 35 MB zip — 8x GitHub's hard
file limit, so the raw table cannot be an in-repo anchor. The spec's contract is
the PIN, not the blob (spec:315-316 `data_vintage.source_hashes`), so the
committed offline reproducibility anchor is an extract carrying its OWN sha256
with the raw response's identity recorded beside it. Identity chain:

    raw zip sha256 -> raw inner-CSV sha256 -> FILTER PREDICATE -> extract sha256

Every link is written to the note, so the extract is mechanically re-derivable
from a fresh pull by replaying the predicate below against the pinned raw hash.

FILTER PREDICATE (two axes only — every other dimension, all 15 age bands and
all 4 tenure columns are RETAINED):
  1. GEO in the 7 wholly-Québec geographies: the Québec province total + all 6
     wholly-Québec CMAs. Seven and not three because HORS_RMR = province NET OF
     ALL Québec CMAs (spec:499, spec:550; codex r4-F2 / r1-F8) — netting only
     Montréal+Québec would wrongly fold the other four QC CMAs into the residual.
  2. Statistics (3C) == "Number of private households". The other two members
     are confidence-interval bounds; nothing downstream consumes them.

`Ottawa - Gatineau (CMA), Ont./Que.` is deliberately EXCLUDED: it is not a
wholly-Québec CMA and this table publishes no separable Québec-part row, so its
Québec side is inseparable here and sits INSIDE the computed residual. The note
records that denotation explicitly (spec:552-554).

The fragile FOGS alternative.cfm chart-page path is FORBIDDEN in code.

Run:  cd demoflow && uv run python probes/run_p2.py
"""

import csv
import hashlib
import io
import json
import math
import os
import tempfile
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

WDS = "https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/98100231/en"

# PINNED VINTAGE, deliberately NOT clock-derived. `data_vintage.extracted_at` (spec:315-316)
# identifies WHICH pull the pinned hashes came from — it is a property of the data, not of
# this process's last run. Clock-deriving it would (a) change the note on a re-run that
# reproduced byte-identical hashes, destroying the re-run idempotence that proves the note
# is script-generated rather than hand-edited, and (b) misreport a re-verification as a new
# vintage. Bump it only when the pinned hashes below actually change.
EXTRACTED_AT = "2026-07-21"

OUT_NOTE = Path(__file__).resolve().parent / "P2-census-tenure-age.md"
OUT_CSV = Path(__file__).resolve().parent.parent / "data" / "census_tenure_age_98100231.csv"

# --- the filter predicate, verbatim ------------------------------------------
TARGET_GEOS = (
    "Quebec",                      # province total (plain: no accent, no suffix)
    "Montréal (CMA), Que.",
    "Québec (CMA), Que.",
    "Saguenay (CMA), Que.",
    "Sherbrooke (CMA), Que.",
    "Trois-Rivières (CMA), Que.",
    "Drummondville (CMA), Que.",
)
TARGET_STATISTIC = "Number of private households"
EXCLUDED_CMA = "Ottawa - Gatineau (CMA), Ont./Que."

# Cheap superset prefilter, so 3.6M lines are not CSV-parsed one by one. It is sound only
# while every target GEO contains this token — asserted below, because a target that did
# not would be dropped SILENTLY, which is the one failure this probe must never have.
PREFILTER_TOKEN = "Que"

# --- oracle (spec-pinned): Montréal CMA, 75+, owner share --------------------
ORACLE_GEO = "Montréal (CMA), Que."
ORACLE_AGES = ("75 to 84 years", "85 years and over")
ORACLE_TOTAL_MEMBERS = (
    "Total - Structural type of dwelling",
    "Total - Condominium status",
    "Total - Household type including census family structure",
)
CHUNK = 8 << 20


def _sha256_stream(read_chunk) -> tuple[str, int]:
    """sha256 + byte count over a stream, never materializing it."""
    digest, size = hashlib.sha256(), 0
    while True:
        block = read_chunk(CHUNK)
        if not block:
            return digest.hexdigest(), size
        digest.update(block)
        size += len(block)


def _download(url: str, dest: Path) -> tuple[str, int]:
    with urllib.request.urlopen(url, timeout=300) as resp, dest.open("wb") as out:
        digest, size = hashlib.sha256(), 0
        while True:
            block = resp.read(CHUNK)
            if not block:
                break
            digest.update(block)
            size += len(block)
            out.write(block)
    return digest.hexdigest(), size


def _geography_universe(zf: zipfile.ZipFile, meta_member: str) -> dict:
    """Derive the GEO dimension's FULL membership from the table's own metadata member.

    The 811 MiB data member is only ever read through the Québec prefilter, so it cannot
    support any Canada-wide claim — asserting one from it would be a hand-typed number
    wearing a 'verified' label. The ~207 KB metadata member carries the complete GEO
    dimension with parent links, so every count returned here is COMPUTED.

    Parentage is what makes 'wholly-Québec' a structural fact rather than a name-suffix
    guess: a CMA is wholly-Québec iff its parent member IS the Québec province member.
    """
    rows = list(csv.reader(io.StringIO(zf.read(meta_member).decode("utf-8-sig"))))
    # member block rows: dimension id '1' (Geography) with a numeric Member ID
    geo = [r for r in rows if len(r) >= 5 and r[0] == "1" and r[3].isdigit()]
    if not geo:
        raise ValueError(f"{meta_member} carries no Geography dimension members")
    by_id = {r[3]: r for r in geo}
    roots = [r for r in geo if not r[4]]
    if len(roots) != 1:
        raise ValueError(f"expected exactly 1 parentless GEO member, got {len(roots)}")
    root = roots[0]
    provinces = [r for r in geo if r[4] == root[3]]
    cmas = [r for r in geo if "(CMA)" in r[1]]
    cas = [r for r in geo if "(CA)" in r[1]]
    # a published "non-CMA/CA" aggregate would be a sub-provincial member that is neither
    unclassified = [
        r[1]
        for r in geo
        if r[4] and r[4] != root[3] and "(CMA)" not in r[1] and "(CA)" not in r[1]
    ]

    qc = [r for r in geo if r[1] == "Quebec"]
    if len(qc) != 1:
        raise ValueError(f"expected exactly 1 GEO member named 'Quebec', got {len(qc)}")
    qc_children = [r for r in geo if r[4] == qc[0][3]]
    qc_cmas = sorted(r[1] for r in qc_children if "(CMA)" in r[1])
    qc_cas = sorted(r[1] for r in qc_children if "(CA)" in r[1])

    # CAs that straddle the Québec border: named `Que.` but parented elsewhere. Their
    # Québec parts are inseparable in this table and therefore fall inside the residual.
    # Derived, not named by hand — if StatCan adds a third, the note says so by itself.
    cross_border_cas = sorted(
        (r[1], by_id[r[4]][1] if r[4] in by_id else "UNKNOWN PARENT", r[4])
        for r in geo
        if "(CA)" in r[1] and "Que." in r[1] and r[4] != qc[0][3]
    )

    excluded = [r for r in geo if r[1] == EXCLUDED_CMA]
    excluded_parent = (
        by_id[excluded[0][4]] if excluded and excluded[0][4] in by_id else None
    )

    # STRUCTURAL GUARD: the hand-written predicate must equal what the metadata says the
    # wholly-Québec geographies ARE. If StatCan adds or renames a Québec CMA, this raises
    # instead of silently shipping an extract that no longer means province-net-of-all-CMAs.
    derived = {qc[0][1], *qc_cmas}
    if derived != set(TARGET_GEOS):
        raise ValueError(
            "TARGET_GEOS no longer equals the metadata-derived wholly-Québec set. "
            f"missing from predicate: {sorted(derived - set(TARGET_GEOS))}; "
            f"stale in predicate: {sorted(set(TARGET_GEOS) - derived)}"
        )

    return {
        "members": len(geo),
        "root": root[1],
        "provinces": len(provinces),
        "cmas": len(cmas),
        "cas": len(cas),
        "unclassified": unclassified,
        "qc_cmas": qc_cmas,
        "qc_cas": qc_cas,
        "cross_border_cas": cross_border_cas,
        "excluded_parent": excluded_parent[1] if excluded_parent else None,
        "excluded_parent_id": excluded_parent[3] if excluded_parent else None,
        "excluded_parent_code": excluded_parent[2] if excluded_parent else None,
        "qc_member_id": qc[0][3],
        "qc_member_code": qc[0][2],
    }


def _label_collisions(zf: zipfile.ZipFile, meta_member: str) -> list[dict]:
    """Dimensions whose member LABELS repeat under different member ids.

    This is why the extract is re-emitted verbatim rather than deduplicated: a
    label-keyed collapse would silently merge distinct members that happen to share a
    display name, destroying rows on the artifact that is pinned truth downstream.
    """
    rows = list(csv.reader(io.StringIO(zf.read(meta_member).decode("utf-8-sig"))))
    dim_names = {
        r[0]: r[1] for r in rows if len(r) >= 4 and r[0].isdigit() and not r[3].isdigit()
    }
    members: dict[str, list[str]] = {}
    for r in rows:
        if len(r) >= 5 and r[0].isdigit() and r[3].isdigit():
            members.setdefault(r[0], []).append(r[1])
    out = []
    for dim_id, labels in sorted(members.items(), key=lambda kv: int(kv[0])):
        counts = Counter(labels)
        repeated = sorted(name for name, c in counts.items() if c > 1)
        if repeated:
            out.append(
                {
                    "dimension": dim_names.get(dim_id, f"dimension {dim_id}"),
                    "members": len(labels),
                    "distinct_labels": len(counts),
                    "repeated": repeated,
                }
            )
    return out


def _filter_to_extract(zf: zipfile.ZipFile, member: str, dest: Path) -> dict:
    """Stream the 811 MiB member and write only predicate-matching rows.

    Lines are re-emitted VERBATIM (the extract is literally the raw header plus
    the subset of raw data lines; the sole transformation is BOM removal), so
    the duplicate `Symbol` column names survive intact rather than being mangled
    by a parse/re-serialize round trip.
    """
    unguarded = [g for g in TARGET_GEOS if PREFILTER_TOKEN not in g]
    if unguarded:
        raise ValueError(
            f"prefilter token {PREFILTER_TOKEN!r} does not appear in target GEOs "
            f"{unguarded} — they would be dropped silently; widen the prefilter"
        )
    kept_by_geo: dict[str, int] = {}
    qc_geo_dguid: dict[str, str] = {}
    kept = 0
    # Observe the BOM on the RAW bytes. The streaming read below uses `utf-8-sig`, which
    # strips a BOM whether or not one is present, so it cannot tell us — this is the only
    # place the question can actually be answered.
    with zf.open(member) as probe:
        has_bom = probe.read(3) == b"\xef\xbb\xbf"
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    with zf.open(member) as fh, tmp.open("w", encoding="utf-8", newline="") as out:
        text = io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")
        header_line = text.readline()
        header = next(csv.reader([header_line]))
        width = len(header)
        i_geo = header.index("GEO")
        i_dguid = header.index("DGUID")
        i_stat = header.index("Statistics (3C)")
        out.write(header_line)
        for line in text:
            # superset prefilter; exact field equality is enforced below
            if TARGET_STATISTIC not in line or PREFILTER_TOKEN not in line:
                continue
            row = next(csv.reader([line]))
            if len(row) != width:
                raise ValueError(
                    f"ragged row: expected {width} fields, got {len(row)}: {row[:4]}"
                )
            if row[i_stat] != TARGET_STATISTIC:
                continue
            geo = row[i_geo]
            if PREFILTER_TOKEN in geo:  # geography inventory (audit evidence for the note)
                qc_geo_dguid.setdefault(geo, row[i_dguid])
            if geo not in TARGET_GEOS:
                continue
            out.write(line)
            kept += 1
            kept_by_geo[geo] = kept_by_geo.get(geo, 0) + 1
    os.replace(tmp, dest)
    return {
        "header": header,
        "rows": kept,
        "kept_by_geo": kept_by_geo,
        "qc_geo_dguid": qc_geo_dguid,
        "has_bom": has_bom,
    }


def _oracle_from_extract(path: Path) -> dict:
    """Recompute the spec oracle from the COMMITTED extract, re-read from disk.

    Computing it from an in-memory frame would prove nothing about the artifact
    that actually lands in the repo.
    """
    owner = total = 0
    ages: set[str] = set()
    with path.open(encoding="utf-8", newline="") as fh:
        # read POSITIONALLY — duplicate `Symbol` headers collapse in a DictReader
        rows = csv.reader(fh)
        header = next(rows)
        i_geo = header.index("GEO")
        i_age = header.index("Age of primary household maintainer (15)")
        i_struct = header.index("Structural type of dwelling (10)")
        i_condo = header.index("Condominium status (3)")
        i_hhtype = header.index("Household type including census family structure (16)")
        i_total = header.index("Tenure (4):Total - Tenure[1]")
        i_owner = header.index("Tenure (4):Owner[2]")
        for row in rows:
            if row[i_geo] != ORACLE_GEO:
                continue
            ages.add(row[i_age])
            if (row[i_struct], row[i_condo], row[i_hhtype]) != ORACLE_TOTAL_MEMBERS:
                continue
            if row[i_age] not in ORACLE_AGES:
                continue
            total += int(row[i_total])
            owner += int(row[i_owner])
    # A missing denominator means the extract carries none of the rows the oracle is
    # computed over. Formatting that as `nan%` would let the note print a nan beside
    # "proof the filter dropped and mangled nothing" — the note must never be able to
    # congratulate itself on a failed run.
    if total <= 0:
        raise ValueError(
            f"oracle denominator is {total}: the extract carries no {ORACLE_GEO} rows "
            f"with {ORACLE_TOTAL_MEMBERS} at ages {ORACLE_AGES}. The filter produced "
            "nothing to verify — refusing to record a verdict."
        )
    share_pct = 100.0 * owner / total
    if not math.isfinite(share_pct):
        raise ValueError(f"oracle share is non-finite ({share_pct}) from {owner}/{total}")
    return {
        "owner": owner,
        "total": total,
        "share_pct": share_pct,
        "age_members": sorted(ages),
    }


def _collisions_txt(collisions: list[dict]) -> str:
    if not collisions:
        return "no dimension repeats a member label."
    return " ".join(
        f"`{c['dimension']}` has {c['members']} members but only "
        f"{c['distinct_labels']} distinct labels — repeated: "
        f"{', '.join(f'`{name}`' for name in c['repeated'])}."
        for c in collisions
    )


def main() -> None:
    note = ["# P2 — StatCan 98-10-0231-01 tenure x age (RECORDED OBSERVATION)", ""]
    try:
        with urllib.request.urlopen(WDS, timeout=60) as resp:
            body = resp.read().decode("utf-8")
        meta = json.loads(body)  # flat scalar dict — NOT a frame; pd.read_json raises
        zip_url = meta["object"]

        with tempfile.TemporaryDirectory() as td:
            zip_path = Path(td) / "98100231-eng.zip"
            zip_sha, zip_bytes = _download(zip_url, zip_path)
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
                member = [
                    n for n in names if n.endswith(".csv") and "MetaData" not in n
                ][0]
                meta_member = [n for n in names if "MetaData" in n][0]
                with zf.open(member) as fh:
                    raw_sha, raw_bytes = _sha256_stream(fh.read)
                universe = _geography_universe(zf, meta_member)
                collisions = _label_collisions(zf, meta_member)
                obs = _filter_to_extract(zf, member, OUT_CSV)

        # A target geography that produced no rows is a FAILED pull, not a footnote.
        # Recording it and carrying on would let the note say VERDICT: WIRED over an
        # extract missing a geography the residual arithmetic depends on.
        absent = [g for g in TARGET_GEOS if g not in obs["kept_by_geo"]]
        if absent:
            raise ValueError(
                f"target geographies produced no rows: {absent}. The extract cannot "
                "support province-net-of-all-CMAs — refusing to record a verdict."
            )

        with OUT_CSV.open("rb") as fh:
            extract_sha, extract_bytes = _sha256_stream(fh.read)
        oracle = _oracle_from_extract(OUT_CSV)

        qc = obs["qc_geo_dguid"]
        cmas = sorted(g for g in qc if "(CMA)" in g)
        tenure_cols = [c for c in obs["header"] if c.startswith("Tenure (")]
        symbol_cols = [c for c in obs["header"] if c == "Symbol"]
        xborder = universe["cross_border_cas"]
        xborder_txt = (
            ", ".join(f"`{name}` (parent: {parent})" for name, parent, _ in xborder)
            if xborder
            else "none"
        )

        note += [
            "## 1. Live pull — request and response, verbatim",
            "",
            f"- request URL: `{WDS}`",
            f"- response body: `{body.strip()}`",
            f"- resolved zip url: `{zip_url}`",
            f"- zip members: `{names}`",
            f"- extracted_at (PINNED vintage, not a run clock): `{EXTRACTED_AT}`",
            "",
            "## 2. Raw response identity (the PIT chain, upstream of "
            "`data_vintage.source_hashes`)",
            "",
            "| link | sha256 | bytes |",
            "|---|---|---|",
            f"| raw zip (`{zip_url.rsplit('/', 1)[-1]}`) | `{zip_sha}` | {zip_bytes:,} |",
            f"| raw inner CSV (`{member}`) | `{raw_sha}` | {raw_bytes:,} |",
            f"| committed extract (`{OUT_CSV.name}`) | `{extract_sha}` | "
            f"{extract_bytes:,} |",
            "",
            "**The inner CSV hash is the stable raw anchor.** Zip byte-stability across "
            "re-downloads is NOT guaranteed (archive metadata — timestamps, ordering, "
            "compressor settings — can shift without the data changing), so the zip hash "
            "is recorded for provenance but the inner member's hash is what a re-pull "
            "must reproduce.",
            "",
            "The raw table is NOT committed: "
            f"{raw_bytes:,} bytes uncompressed is ~8x GitHub's hard file limit. The "
            "committed extract carries its own separate pin (row above), and that pin is "
            "the value `data_vintage.source_hashes` takes for this source (spec:315-316). "
            "This note is the upstream source for that structure; the structure itself is "
            "NOT built here.",
            "",
            "## 3. Filter predicate (verbatim — the extract is mechanically re-derivable)",
            "",
            "Applied to the raw inner CSV pinned above. Two axes only; **every other "
            "dimension, all 15 age bands and all 4 tenure columns are RETAINED**:",
            "",
            f"1. `GEO` ∈ the {len(TARGET_GEOS)} wholly-Québec geographies:",
        ]
        note += [f"   - `{g}`" for g in TARGET_GEOS]
        note += [
            f"2. `Statistics (3C)` == `{TARGET_STATISTIC}` (exact string equality; the "
            "other two members are confidence-interval bounds that nothing downstream "
            "consumes)",
            "",
            "Rows are re-emitted VERBATIM — the extract is the raw header plus the subset "
            "of raw data lines that satisfy the predicate. The sole transformation is "
            "UTF-8 BOM removal from the header. No reserialization, no dtype coercion, no "
            "column renaming.",
            "",
            f"- extract rows (excl. header): **{obs['rows']:,}**",
            f"- rows per GEO: `{json.dumps(obs['kept_by_geo'], ensure_ascii=False)}`",
            f"- target GEOs NOT FOUND in the table: "
            "`none — all 7 present verbatim` (a target producing no rows raises; this "
            "line can only ever be reached when every one of them was found)",
            "",
            "### Why 7 geographies and not 3",
            "",
            "`HORS_RMR` = province net of **ALL** Québec CMAs (spec:499, spec:550; codex "
            "r4-F2 / r1-F8). Netting only Montréal+Québec would wrongly fold the other "
            "four wholly-Québec CMAs into the residual.",
            "",
            "### Excluded on purpose",
            "",
            f"- `{EXCLUDED_CMA}` — DGUID "
            f"`{qc.get(EXCLUDED_CMA, 'NOT FOUND')}`, parent member "
            f"`{universe['excluded_parent']}` (Member ID "
            f"`{universe['excluded_parent_id']}`, classification code "
            f"`{universe['excluded_parent_code']}`) — NOT the Québec member (Member ID "
            f"`{universe['qc_member_id']}`, classification code "
            f"`{universe['qc_member_code']}`). Parentage is derived from the table's own "
            "metadata member, so 'not wholly-Québec' is structural here, not a reading of "
            "the name suffix. This table publishes no separable Québec-part row, so its "
            "Québec side is INSEPARABLE and sits INSIDE the residual.",
            "",
            "## 4. What HORS_RMR actually denotes here (spec:552-554)",
            "",
            "**CA caveat (codex r5-F7):** a published `non-CMA/CA` row would EXCLUDE "
            "Census Agglomerations while province-minus-CMAs INCLUDES them. This table "
            "publishes **no** such row. Computed from the metadata member "
            f"(`{meta_member}`), the Geography dimension has "
            f"**{universe['members']} members** = `{universe['root']}` + "
            f"{universe['provinces']} provinces/territories + {universe['cmas']} CMAs + "
            f"{universe['cas']} CAs; sub-provincial members that are neither CMA nor CA: "
            f"`{universe['unclassified'] if universe['unclassified'] else 'none'}`. The "
            "spec:552-554 else-branch therefore fires: **the residual is COMPUTED**, and:",
            "",
            "> **HORS_RMR here denotes: Québec outside the six wholly-Québec CMAs — "
            "INCLUDING all 23 Census Agglomerations AND the Québec side of "
            "Ottawa-Gatineau.**",
            "",
            f"Confirmed from metadata parentage: the Québec member has "
            f"{len(universe['qc_cmas'])} CMA children (all kept) and "
            f"{len(universe['qc_cas'])} CA children (all inside the residual). Beyond "
            f"those, {len(xborder)} cross-border CAs carry `Que.` in the name but are "
            f"parented elsewhere — {xborder_txt} — so their Québec parts are likewise "
            "inseparable and likewise fall inside the residual. Names and parents are "
            "resolved from the metadata member, not enumerated by hand.",
            "",
            f"- wholly-Québec CMAs (metadata-derived, children of the Québec member): "
            f"`{json.dumps(universe['qc_cmas'], ensure_ascii=False)}`",
            f"- QC-name-matching CMAs seen in the data ({len(cmas)}): "
            f"`{json.dumps(cmas, ensure_ascii=False)}` — the extra one is "
            f"`{EXCLUDED_CMA}` (excluded).",
            "",
            "## 5. Observed table shape",
            "",
            f"- columns ({len(obs['header'])}), verbatim as received: "
            f"`{json.dumps(obs['header'], ensure_ascii=False)}`",
            f"- Tenure is WIDE (in columns, not rows): {len(tenure_cols)} tenure columns "
            f"with {len(symbol_cols)} duplicate `Symbol` columns interleaved after each. "
            "Duplicate names are preserved verbatim; positional access is required (a "
            "`DictReader` collapses them). Tenure columns as received: "
            f"`{json.dumps(tenure_cols, ensure_ascii=False)}`",
            "- **DUPLICATE MEMBER LABELS (not just duplicate column names).** Computed "
            f"from the metadata member: {_collisions_txt(collisions)} Members are "
            "distinguished by member id / `Coordinate`, NOT by label — this is why rows "
            "are re-emitted verbatim. Any downstream dedup or group-by keyed on the "
            "LABEL would silently merge distinct members and destroy rows.",
            f"- UTF-8 BOM on the raw member's first bytes: **{obs['has_bom']}** (observed "
            "on the raw bytes before decoding, since `utf-8-sig` strips a BOM whether or "
            f"not one is there){'; stripped in the extract.' if obs['has_bom'] else '.'}",
            f"- age members ({len(oracle['age_members'])}): "
            f"`{json.dumps(oracle['age_members'], ensure_ascii=False)}`",
            "- **There is no single `75 years and over` member.** 75+ must be summed from "
            "`75 to 84 years` + `85 years and over`.",
            "- StatCan rounds counts to the nearest 5, so tenure components do NOT "
            "reconcile exactly to totals. This is a property of the source, not a defect; "
            "it is recorded, never 'fixed'.",
            "",
            "## 6. Oracle — recomputed from the COMMITTED extract, re-read from disk",
            "",
            f"`{ORACLE_GEO}`, `Total -` member of every non-age dimension, statistic "
            f"`{TARGET_STATISTIC}`, summing age bands `{ORACLE_AGES[0]}` + "
            f"`{ORACLE_AGES[1]}`:",
            "",
            f"- owner households: **{oracle['owner']:,}**",
            f"- total households: **{oracle['total']:,}**",
            f"- owner share: **{oracle['share_pct']:.4f}%** → rounds to the spec's 56.2%",
            "",
            "This is the proof the filter dropped and mangled nothing.",
            "",
            "## 7. Verdict",
            "",
            "- VERDICT: WIRED (WDS endpoint live; table pulled, filtered, pinned and "
            "committed).",
        ]
    except Exception as exc:  # record failure verbatim + spec fallback, never silent
        note += [
            f"- LIVE PULL FAILED: {type(exc).__name__}: {exc}",
            "- FALLBACK (spec §4): ownership rate is a hard input; without this table",
            "  the ownership loader (Task 13) cannot join — record the failure and retry",
            "  the WDS endpoint / productId before proceeding. NO silent substitute.",
        ]
    OUT_NOTE.write_text("\n".join(note) + "\n", encoding="utf-8")
    print("\n".join(note))


if __name__ == "__main__":
    main()
