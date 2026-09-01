# HORS_RMR residual bracket — the measured record (Task 26, 2026-08-15)

**What this is.** The measured whole-CD bracket for HORS_RMR's immigrant operands: settled persons,
headship and the immigrant/non-immigrant ownership ratio, for the shipped residual and the three
alternative residual constructions. Measured via **98-10-0622-01** (a ruled one-universe source
under steering ruling T), on the same date as the Task-26 re-triage.

**Why it exists as its own public record.** `demoflow/probes/run_p10.py` recomputes eight of these
figures from live data and its `_guard_citation` refuses unless each recomputed value appears
verbatim in the record it cites — a cross-document coupling check that detects drift between a live
recomputation and the historical measurement. That guard is only meaningful against a document
authored INDEPENDENTLY of the probe's own emission: pointing it at the probe's output
(`probes/P10-hors-operand-alignment.md`) would make the probe verify itself, which is a check that
cannot fail. This record is therefore the independent half of that pair, and it is public so that
the shipped test suite has no read outside what ships. (Spec amendment #29, 2026-08-23 — the read it
replaces resolved into an internal dispatch record, which made 16 tests in the public suite
unrunnable from any checkout that did not carry internal ledger files.)

## The bracket

| residual variant | settled persons | HEADSHIP | RATIO |
|---|---:|---:|---:|
| as shipped (Gatineau IN) | 84,785 | 0.5169 | 0.9600 |
| − CD Gatineau (2481) | 50,515 | 0.5218 (+0.95%) | **1.0320 (+7.50%)** |
| − CD Gat + Collines | 48,210 | 0.5228 (+1.15%) | 1.0242 (+6.69%) |
| − CD Gat + Coll + Papineau | 47,790 | 0.5218 (+0.94%) | 1.0230 (+6.56%) |

Variant labels are reproduced exactly as measured; the probe's own `bracket` keys are what bind a
label to a variant, never this table's row order.

## What the bracket establishes

**The immigrant ratio as shipped is not sound, and the two errors ADD.** `h_imm` and `r_imm` are
numerator-only, have no cancellation channel, and MULTIPLY inside `D_imm`, so their same-signed
relative errors compound: `h×r` moves **0.49622 → 0.53850**, understating HORS_RMR's immigrant
demand leg by roughly **7.6%–8.5%** across the bracket.

**It is qualitative, not merely quantitative: 0.9600 → 1.0320 crosses 1.0.** As shipped, settled
immigrants at HORS_RMR read as owning at a DISCOUNT to non-immigrants; across the bracket they read
as owning at a PREMIUM. The sign of the effect, not just its size, depends on the residual.

**Why a person-weighted correction understates it.** The 12.99% / 14.93% figures recorded earlier are
TOTAL-PERSON weights, but both new quantities are immigrant-denominated, and **CD Gatineau holds
40.42% of the residual's `Before 2016` stock against a 10.35% person weight — 3.9× the person-weighted
figure.** Immigrants concentrate in the one urban area inside the residual, so weighting by persons
mis-sizes the correction.

## Scope, and the one thing this record cannot protect

These are MEASUREMENTS on a named source at a named date, not a ruling: which residual demoflow
ships is decided in the spec, not here.

**The guard that reads this file compares digits, so it cannot tell a re-measurement from a
re-typing.** Editing a figure here and leaving the probe's live recomputation to agree with it is
exactly the attack the coupling cannot see — the same shape as editing a pinned span and re-minting
its digest in one commit. What defends against it is that the recomputation is derived from source
data rather than from this table: a digit changed here alone REDS, and a digit changed here to match
a changed recomputation is a deliberate act that must be justified at the spec, with the measurement
re-run against 98-10-0622-01. Never update this record to make a red go away.
