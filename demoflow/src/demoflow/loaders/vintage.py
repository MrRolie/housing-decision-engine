"""Typed rate-surface vintage — what a CONSUMER of a rate table must be able to state.

WHY THIS MODULE EXISTS (run-6 carry, 2026-08-13). Every rate loader in this package
verifies its artifact's provenance on the way in and then returns the `rates` sub-tree
ALONE: `_provenance` is dropped at the boundary. That was harmless while the only consumers
were tests, and stops being harmless with the first production consumer (demand, spec §6),
because spec §7 makes the emitted artifact publish `data_vintage.source_hashes` for exactly
these surfaces. A consumer that cannot say which vintage produced the numbers it is holding
cannot fill that envelope from what it loaded — it can only re-derive the vintage from the
files at emit time, which is a DIFFERENT claim: it says what is on disk now, not what the
run actually read.

SCOPE, deliberately narrow: this is a RECORD, not a gate. The tempting gate — "refuse a
demand number computed from an ownership surface and a headship surface at different
vintages" — cannot fire: both artifacts are checked against the SAME pins registry on every
load (steering ruling L), so they cannot disagree, and a check that cannot fail is not a
check. What is checkable here is that a vintage is COMPLETE (dated, sourced, digested), and
that is asserted: an envelope field that silently degrades to "" or {} publishes an artifact
that merely LOOKS provenanced.

ONE BUILDER, TWO PROVENANCE SHAPES, by measurement rather than by preference: headship
records a `sources` MAP (it derives from two files — the Census extract and the ISQ person
denominator), while ownership records a single `source` + `sha256`. Both shapes are read
here, so neither of the two surfaces that HAVE a vintage accessor needs a bespoke reader.

SCOPE OF THAT CLAIM, narrowed to what is measured (2026-08-14): it covers ownership and
headship. `living_arrangement` carries the single-source SHAPE too, but spells its date
`ref_date`, so `vintage_from_provenance` refuses it today. That is not a latent bug — the
surface has no vintage consumer yet — and the fix is the rename ownership already took
(`ref_date` -> `as_of`, one date spelled the way `Anchor` spells it), to be done WITH that
consumer so the loader, the generator and the artifact move together. Recorded here rather
than papered over with a synonym, which would leave two spellings of one field in the tree.
"""
from dataclasses import dataclass

from demoflow.errors import LoaderError

_SHA256_HEX_LEN = 64


def _hexdigest(value: object, ctx: str) -> str:
    """A digest that is not 64 hex characters is not a digest.

    Checked at the point the record is BUILT rather than at the emitter (spec §7's
    `write_json_strict` re-checks 64-hex on the way out): a truncated or placeholder digest
    that reaches the emitter has already been carried through a whole run as if it identified
    something.
    """
    if not isinstance(value, str) or len(value) != _SHA256_HEX_LEN:
        raise LoaderError(f"{ctx}: {value!r} is not a 64-hex sha256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise LoaderError(f"{ctx}: {value!r} is not a 64-hex sha256 digest") from exc
    return value


def _nonempty(provenance: dict, field: str, artifact: str) -> str:
    value = provenance.get(field)
    if not isinstance(value, str) or not value.strip():
        raise LoaderError(
            f"{artifact}: `_provenance.{field}` is {value!r} — a rate surface that records no "
            f"{field} cannot state its vintage, and an undated or uncited record is a defect "
            "(constants.py's charter rule)")
    return value


@dataclass(frozen=True)
class RateVintage:
    """The vintage of ONE rate surface, in the shape spec §7's envelope wants.

    `sources` is a sorted tuple of (file, sha256) pairs rather than a dict so the record is
    hashable and frozen all the way down — a vintage that a consumer can mutate is a vintage
    that can disagree with the artifact it came from.
    """

    artifact: str
    as_of: str
    sources: tuple[tuple[str, str], ...]
    raw_source_sha256: str | None
    raw_source_name: str | None
    extracted_at: str

    def source_hashes(self) -> dict[str, dict[str, str]]:
        """spec §7 `data_vintage.source_hashes`: {source: sha256-OF-RAW-RESPONSE, extracted_at}.

        The value is the RAW-RESPONSE digest (codex r3-F6: "every non-ISQ source's RAW RESPONSE
        is hashed at extract time and the hash is part of artifact identity (ISQ files are
        already byte-pinned)"), which is NOT always the digest recorded in `sources`:

          * A source cut from an uncommittable upstream member — the Census extract — sits one
            link down pins.py's chain (raw response -> filter predicate -> committed extract ->
            derived rates). Its `sources` digest names the EXTRACT. Publishing that under a §7
            field defined as the raw response names an object a reader cannot re-derive the
            artifact from, and one that a re-cut moves with — which is the entire reason the
            separate `RAW_SOURCE_SHA256` anchor exists. So the raw anchor is substituted here.
          * A byte-pinned ISQ workbook IS its own raw response (r3-F6's parenthetical), so its
            recorded digest is already the raw-response digest and is emitted unchanged.

        Measured 2026-08-14 before this was split: the map emitted the committed-extract digest
        for the Census source while the record carried the raw anchor and dropped it. The defect
        was invisible precisely because the ISQ entry alongside it was correct — one map, two
        silently different semantics, under a single field name.
        """
        return {name: {"sha256": (self.raw_source_sha256 if name == self.raw_source_name
                                  else sha),
                       "extracted_at": self.extracted_at}
                for name, sha in self.sources}


def vintage_from_provenance(artifact: str, provenance: dict,
                            raw_source_name: str | None = None) -> RateVintage:
    """Build the typed vintage from an artifact's own `_provenance` block.

    Reads the artifact's RECORDED source digests — never a fresh hash of the artifact file —
    so the record names the UPSTREAM vintage the rates were derived from, which is the thing
    a reader of the emitted envelope needs in order to re-derive them.

    `raw_source_name` is the OTHER half of `_provenance.raw_source_sha256`: WHICH source that
    upstream digest anchors. It is supplied by the caller rather than read from the artifact
    because the caller (census.py) is already the thing that verified the anchor against
    `pins.raw_anchor(...)`, so the association is stated at the same place it is checked
    instead of being re-derived from a second recorded field that could drift from the first.
    Ownership has one source and reads unambiguously either way; headship has TWO, and there
    the association was carried by convention alone — the shape in which `source_hashes()`
    silently published a committed-extract digest under a raw-response field. A digest with no
    name, a name with no digest, and a name that is not one of the sources all REFUSE.
    """
    if not isinstance(provenance, dict):
        raise LoaderError(f"{artifact}: no `_provenance` block — no vintage can be stated")

    sources_map = provenance.get("sources")
    if isinstance(sources_map, dict) and sources_map:
        sources = tuple(sorted(
            (name, _hexdigest(sha, f"{artifact}: `_provenance.sources[{name}]`"))
            for name, sha in sources_map.items()))
    elif provenance.get("source") and provenance.get("sha256") is not None:
        name = provenance["source"]
        sources = ((name, _hexdigest(provenance["sha256"],
                                     f"{artifact}: `_provenance.sha256` for {name}")),)
    else:
        raise LoaderError(
            f"{artifact}: `_provenance` records neither a `sources` map nor a "
            "`source`+`sha256` pair — the rates have no identified origin")

    # Optional by design: only surfaces cut from an uncommittable raw member carry an upstream
    # anchor (DIV F2). Present-but-malformed still refuses — a half-recorded anchor is worse
    # than an absent one, because it reads as verified. The name/digest PAIRING is refused the
    # same way and for the same reason: `source_hashes()` substitutes the raw digest for
    # exactly one key, so an anchor that names nothing (or names a non-source) would either
    # vanish from the envelope or be published against the wrong object.
    raw = provenance.get("raw_source_sha256")
    if raw is not None and raw_source_name is None:
        raise LoaderError(
            f"{artifact}: `_provenance.raw_source_sha256` is recorded but the caller names no "
            "source for it — an upstream digest that anchors nothing identifiable cannot be "
            "published as spec §7's sha256-of-raw-response for any key")
    if raw_source_name is not None:
        if raw is None:
            raise LoaderError(
                f"{artifact}: raw source named {raw_source_name!r} but the provenance records "
                "no `raw_source_sha256` — the anchor the name points at is absent")
        if raw_source_name not in dict(sources):
            raise LoaderError(
                f"{artifact}: raw source {raw_source_name!r} is not among the recorded sources "
                f"{sorted(dict(sources))} — the upstream anchor would be published under a key "
                "no reader can tie back to a source of these rates")
    return RateVintage(
        artifact=artifact,
        as_of=_nonempty(provenance, "as_of", artifact),
        sources=sources,
        raw_source_sha256=None if raw is None else _hexdigest(
            raw, f"{artifact}: `_provenance.raw_source_sha256`"),
        raw_source_name=raw_source_name,
        extracted_at=_nonempty(provenance, "extracted_at", artifact),
    )
