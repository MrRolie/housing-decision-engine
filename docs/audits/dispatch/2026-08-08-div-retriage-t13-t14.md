# DIV re-triage discharge record — Tasks 13 + 14 (seat-dispatched, 2026-08-08)

Two standing data-integrity-validator debts (plan adversarial-review template) discharged as
parallel seat-side dispatches at the run-6 fold. Full verdicts in the seat transcript; this
record carries the rulings.

## div-t14-ircc — PASS-WITH-NOTES (loader) + 1 FINDING routed to Task 28
Loader holds on live bytes (21,217×11; all charter facts reproduce; schema gates refuse 8/8
drift classes; Wayback 2.5-year schema stability; grain clean; fixture byte-verbatim).
FINDING (Task 28 scope mismatch): plan constant 45,000 is PROVINCIAL, reference realized is
the CMA PAIR (2025: 45,895 vs province 60,000; pair share decays ~4pp/yr; the near-match is
two mismatched scopes coinciding). RULINGS → charter Task 28 (five binding design inputs:
computed realized, provincial numerator, plan-era time axis, ≥5-month freshness limit +
12-distinct-months completeness, all-suppressed floor guard) + Task 30 (restatement-aware
golden: record feed vintage; regen from the pinned local copy).

## div-t13-census — FINDINGS (ownership derivation SOUND; headship WRONG)
- CONFIRMED: territory-note arithmetic exact (7 RMR rows + hors-RMR sum to province, Δ=0);
  ownership schema drift REFUSES (member renames raise); numerator closure exact (banded
  maintainers 3,749,040 vs total 3,749,035 = round-to-5).
- F1 ESCALATE (live defect): headship_by_age.json values do NOT reproduce from their stated
  source at their use site (spec OwnerStock multiplies ISQ scenario population): derived vs
  typed — 20-34 0.395/0.40, 35-54 0.578/0.48 (−16.9%), 55-64 0.611/0.52, 65-74 0.640/0.56,
  75+ 0.592/0.62 (+4.7%, SHAPE INVERTED — real curve dips after 65-74); aggregate −9.5%
  households (3,393,953 vs 3,749,035). 0-19 band incommensurable as typed. Adverse both
  directions (overstates 75+ release, understates absorbers).
- F2 ESCALATE (regrade): the disclosed "on-disk swap" gap is benign alone, but the COMPOSITE
  legitimate-refresh motion (re-extract + re-pin + regen) passes 19/19 on a materially wrong
  table — every gate compares co-moving objects; sole external anchor = 1 of 12 cells.
- F3: the territory-note gate pins figure PRESENCE, not ROLE (swapped territories pass).
- Lens notes: loaders drop vintage at the return boundary (deadline = first production
  consumer, plan:4661); two refusals raise with misdirecting messages; gap (c)
  CONFIRM-ACCEPTABLE with the named trigger (plan:4661 passes data_dir=).

## Seat disposition
FIX-FORWARD TASK QUEUED (T13b, dispatches at run-7 close — worktree occupied until then):
(1) headship RE-DERIVED from the committed pinned sources via a generator + full-table
oracle + regen-equality + ruling-L identity gate (the ruling-B/census pattern; use-site
semantics rule; 0-19 handled by the use-site rule or dropped if unconsumed); (2) the P2
inner-CSV sha256 (773f7af8…) promoted from probe-note prose into pins/_provenance as the
refresh-path external anchor, + 2 additional spec-oracle cells from P2's recorded values;
(3) territory-note gate made role-sensitive (contiguous-clause assertion, ca_caveat
pattern); (4) misdirecting refusal messages named. Vintage-through-returns rides the first
production-consumer task (25/26) as a carry, not T13b.
