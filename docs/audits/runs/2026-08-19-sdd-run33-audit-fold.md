# Seat-run dispatch record — run 33 (fold the pre-PR audit gates)

- date: 2026-08-19
- script: `mm-spine/.claude/workflows/mm-sdd-pipeline.js` sha256
  `d7743e42b0ebe6499f8f5af986b471ea3417aff067710048dc39aa8756e315ea`
- args: `2026-08-19-sdd-run33-audit-fold.args.json` (sha256
  `2e561f62b4aec2949b95fba70ad725c8d537adadc0a079523dbd532904226385`)
- models: opus/opus; load_bearing ×3; money_path: false
- preconditions, DERIVED from the seat's own gate run: code tree as of `48513b3`, hde **191** +
  demoflow **1097**, tree clean

## The mandate POINTS at the evidence instead of retyping it

The three gate verdicts are COMMITTED at `docs/audits/{quant,stress,data}/2026-07-21-demoflow-tranche1.md`,
and the mandate names each finding by gate and number rather than re-transcribing its claim, evidence
and fix. **A mandate that retypes its own evidence is a transcription channel**, and this arc has paid
for that lesson repeatedly — most recently in run 29, where withholding 31 member names from a mandate
caught a real line-wrap corruption. Where the seat overrides a gate's proposed fix it says so
explicitly and the seat's ruling wins.

## Task order, and the seat says which part it MEASURED

1 identity coverage → 2 contract seams → 3 the sweep and a SINGLE golden re-mint. Tasks 1 and 2 change
the envelope and the record contract, so a golden minted before them would be re-minted anyway.
**Stated in the mandate as a precaution rather than a measurement** — run 31's task order was justified
by "several of these change what the artifacts contain" and the reviewer measured that FALSE. The seat
has not measured the byte deltas of tasks 1 and 2 here and says so in the mandate itself.
`tests/test_golden.py` is expected RED through tasks 1 and 2; the mandate tells the implementer to
report that rather than paper it, and forbids an early regeneration to make it green.

## RULED HERE: the non-finite band is a RUN-LEVEL TERMINAL (data F2)

The gate found the third producer/contract seam and **correctly refused to choose the fix**, calling it
amendment territory under the #16 precedent. The seat rules **option (b)**: a non-finite band endpoint
is a run-level terminal, not an UNKNOWN record.

The band is the CALLER's, injected — so a non-finite band is a caller/config defect, deterministic and
independent of the feed, which is the shape of a terminal and not of a per-indicator UNKNOWN. **The
module already ruled the sibling case exactly this way**: `_band_endpoints` raises a named terminal for
a NON-COERCIBLE endpoint because it cannot ride the record's float-typed band fields — and a non-finite
endpoint cannot ride them either under §7's `allow_nan=False`. Option (a) would send two near-identical
defects down opposite paths and would cost TWO spec amendments to accommodate a caller defect. **The
FINITE inversion case keeps its UNKNOWN(`malformed_band`)**, so §7c's "inverted band → UNKNOWN" stays
exactly true. Spec **amendment #17** is seat-authored at fold, in the same commit as the code.

## The generalizable instruction, worth more than any individual fix

All three seams share one shape — a PRODUCER and its CONTRACT disagreeing, green because no test
crosses them. The mandate therefore asks for the amendment-#16 test shape GENERALIZED: **assert that
every record each producer can emit validates against its contract validator, parametrized over the
full sub-case set.** That single property would have caught all three.

## Deliberately ABSENT: quant F2, the scope fork

The banded-headship-curve artifact in `D_native` (68–100% of it, ~2.5× the ranked signal, reorders all
eight rows) is **not in this run**. Landing an age-resolved curve is new modelling work and the
alternative is shipping with a row-level caveat — a call about what the deliverable is for, which sits
with the operator. The mandate names it as absent and forbids touching the headship curve or extending
the ownership lattice below 25 (spec §7 amendment #12's ordering constraint).

**Routing note:** the seat attempted to send this fork to the mm-infra master steering seat, as the
operator authorized. Three address forms were tried against the `ListAgents` row and none resolved —
**the peer channel is not reachable from this session.** Recorded as a property of the attempt, not as
a conclusion about the peer: the fork is surfaced to the operator directly instead, and this run
proceeds with everything that is not the fork.

- run id: (appended at dispatch)
- outcome: (appended at run close)
