# Seat-run dispatch record — run 25 (P11 closeout + sentence corrections)

Successor to run 24, which the seat STOPPED after its task 2 stalled following a seat-caused process
incident. Task 1 (P10 closeout) completed APPROVE and its work stands; task 3 never started.

- date: 2026-08-15
- script: `mm-spine/.claude/workflows/mm-sdd-pipeline.js` sha256
  `d7743e42b0ebe6499f8f5af986b471ea3417aff067710048dc39aa8756e315ea` @ mm-spine `f4d7cca`
- args: `2026-08-15-sdd-run25-p11-closeout-sentences.args.json` (sha256
  `8e4fe1457305823d3b87ba6a0e667101f5e8dbc4d6634a4cce7435dc1880d6ba`)
- models: opus/opus; load_bearing ×2; money_path: false ×2; WAVE-0 vacuous
- preconditions (GROUND FIRST, seat's own run): suites hde 191 + demoflow **696** with P10's and
  P11's files present; run 24 TaskStopped; checkout now free

## Why a closeout rather than a rebuild

P11's deliverable is COMPLETE and GREEN — 641-line `hors_aligned` module, 648-line test file, the
CSD extract and aligned artifact, a pins row, and `census.py` refactored to expose public seams — but
**it never reached a review stage**, because the workflow stalled first. Green and unreviewed is the
state this arc treats as unproven, so the successor reviews rather than rebuilds. Same shape as the
T13b and P10 closeouts.

## The unusual asset this run has: a free independent measurement

The instance that stood down in the incident had already completed its own live 272-cell pull of
98-10-0232-01 with its OWN member resolution and coordinate builder. Every ρ figure matches P10's
table digit for digit, and it measured a corner nobody had: **at the suppression bound the spread
WIDENS to 1.212 pp** (from 1.2024), so the adverse structure that justified reversing #12(B) holds at
both corners rather than being a point estimate. The mandate hands the closeout that measurement as
the CHECK on the committed artifact — a disagreement is a finding — plus two non-co-moving external
anchors and the correctly-scoped ρ-side suppression census (13 cells at 7 of 16 subdivisions, all
75+ band, a different set from the settled side's 7). Its raw pull is preserved and reusable.

## Verification the mandate demands

The T13b pattern the deliverable claims: pins row and checksum, byte-identical regeneration from the
committed generator, no-drift gate, non-co-moving external anchors, field-wise suppression bounds.
Plus two things specific to this change: **the scope fence is a finding if breached** — it re-points
HORS_RMR ONLY, and any other geography moving is a finding, not rounding — and **`load_ownership_rates`
must NOT be re-pointed**, because the committed T13b external-anchor gates pin HORS_RMR's shipped
residual at `rel=1e-12` and re-pointing would red ruled gates before §6 records the reversal. The
aligned curve lands BESIDE the shipped one with the join explicit. The `census.py` public-seam
refactor (including the `MAINTAINER_TOTAL_MEMBER` rename) must be shown to break no consumer.

## Advisor discipline

- `ADVISOR RULING SKIPPED @run-25 dispatch — no new ruling. The #12(B) reversal was ruled at
  @p10-fork and is unchanged; this run verifies an existing deliverable against it. The
  closeout-not-rebuild disposition cites the arc's own precedent (T13b delivery, run-12 T22
  mechanism, P10 closeout) and the incident handling is recorded, not re-decided.`

- run id: `wf_523b798d-66d` (dispatched 2026-08-15; task id w82gzaoqz)
- outcome: (appended at run close)
