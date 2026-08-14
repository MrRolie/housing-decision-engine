# Seat-run dispatch record — run 17 (P8 successor: build the probe under rulings Q and R)

Successor to run 16 (`wf_caef870f-16d`), which HALTED with a SEAT_QUESTION and built nothing — the
correct outcome. A halt has no resume: fresh dispatch. The ground it halted on is now settled by
operator rulings Q and R, amended into spec §6 as amendment #8 (`1f6eacb`).

- date: 2026-08-14
- script: `mm-spine/.claude/workflows/mm-sdd-pipeline.js` sha256
  `d7743e42b0ebe6499f8f5af986b471ea3417aff067710048dc39aa8756e315ea` @ mm-spine `f4d7cca`
- args: `2026-08-14-sdd-run17-p8-successor.args.json` (sha256
  `ab5b0ae9f3296d240e27124b61d1f1e1993d697086f29ce0dffb6e00a714b98b`)
- models: opus/opus; load_bearing ×1; money_path: false; WAVE-0 vacuous
- preconditions (GROUND FIRST, seat's own run): tree clean at HEAD `1f6eacb`, `./scripts/test-all.sh`
  green at hde 191 + demoflow 396, checkout free

## What the successor must do differently from its predecessor

1. **Build it.** The halt's evidence is scratchpad-only and explicitly NOT an earned verdict —
   everything published gets re-derived through the gated probe.
2. **All five ownership readings as Facts**, not three: the halt's table carried non-immigrant,
   all-immigrant and recent(<10y); the seat added settled(>10y) and NPR, and those two are what
   turned the disposition. The recency spread is the evidence base for the cost §6 records and the
   input a Tranche-2 decision will read.
3. **Pinned coordinates and member ids** so the probe reproduces the seat's exact cells rather than
   re-discovering them — with the instruction that a member resolving differently is a FINDING, not
   a typo to paper over.
4. **Ruling R's transported values COMPUTED, never typed**, from the tree's own committed surfaces,
   and asserted against the figures §6 now states. Carries the enum gotcha the seat hit live:
   `Series.astype(str)` yields the REPR (`<Scenario.REFERENCE: 'reference'>`), so a string filter
   silently matches nothing — sibling of run-1's `str(Geography.X)` carry.
5. **The floor gate as an executable, mutation-tested check** — transported headship must exceed the
   immigrant living-alone share at the same geography — not a sentence.
6. **The absence stated as SCOPED** to the title-selected pool, never as "does not exist". §6 now
   says so in the spec itself, because this arc has twice had an absence claim turn out to be a
   property of the search.
7. **The `\xa0` junction gotcha** named: this cube's geography labels carry trailing non-breaking
   spaces — the arc's 2026-07-21 label class. Key off member ids.

## Advisor discipline

- `ADVISOR RATIFY FIRED @amendment-8` — the RATIFY check on the amendment text before it landed
  durably. Verified all 12 ratios, the floor values, the ~3-8% netting arithmetic and the sweep
  counts as entailed by the seat's own measurements, and confirmed the restructure-to-resolved-present
  did not exceed what was ruled. Two gaps caught and fixed before commit: (a) the headship recipe was
  under-pinned — "seat-computed against the ISQ reference fan at 2026" conflated fan with scenario
  and omitted the aggregation method, so it did not reproduce; now states the population-weighted
  aggregate of the banded curve over `pop-as-rmr-base.xlsx`, `Scenario.REFERENCE`, 2026, with the
  household/person counts; (b) the P4 anchors' survival went silent in the rewrite while "sweep
  unchanged" stayed — readable as licence to cull the very constants `SWEEP_GRID` sources its span
  from. Both now explicit.
- `ADVISOR RULING FIRED @p8-halt-disposition` — logged in run 16's record.

- run id: `wf_025924cf-5fd` (dispatched 2026-08-14; task id w997opqt6)
- outcome: (appended at run close)

## API-529 death and resume (2026-08-14)

First attempt died on `API Error: 529 Overloaded` — server-side transient, not a defect in the work.
Here the IMPLEMENTER died (0 stages completed), leaving a partial `demoflow/probes/run_p8.py` (1,257
lines, structurally complete with a `main()`, but never run to generate its note and never reviewed).

**Seat call: the partial was MOVED to scratchpad (`died-run17/run_p8.partial.py`), not kept and not
deleted.** Kept, it would have met the resumed implementer as a file it has no memory of writing,
against a mandate that says CREATE — and worse, an unreviewed artifact from a died agent could have
become the basis of a note whose provenance header claims live regeneration. Deleted, the bytes
would be gone. Moving restores the recorded dispatch precondition (tree clean) while preserving them.

Resumed under the SAME run id, args unchanged; the implementer re-runs live because it never
completed. A died stage is not a findings-exit, so no successor is needed.

- resumed: 2026-08-14 (task id wj3z2aaqa, same run id `wf_025924cf-5fd`)

### Seat error at this fold, owned

Writing the note above, the seat's first attempt ran the heredoc with the shell cwd still in
`actuarial-system.cf1` — so this demoflow record was created and COMMITTED inside the actuarial
repo (`3178d48`). This is the exact cwd-persistence trap logged as a near-miss at the 2026-08-08d
fold, hit for real this time. Caught immediately by the push failing (`src refspec
feat/demoflow-tranche1 does not match any` from the actuarial remote), which is the only reason it
surfaced — the commit itself was silent and green.

Repaired with the lowest-risk operation available, because that tree holds ~190 tests of
UNCOMMITTED work: the 14 held paths were tar-snapshotted to scratchpad first, then `git reset
--mixed HEAD~1` (which by definition does not touch the working tree) and `rm` of the stray file.
Verified after: HEAD back to `0a115f1` and in sync with origin, 14 held paths still present, suite
376 green. The stray commit was never pushed.

Standing correction, stronger than the 08-08d habit that failed to prevent this: a heredoc block
that writes into a repo states its `cd` **inside the same command**, never inheriting cwd from a
prior call — and the `git add`/`commit` pair rides in that same block. Relative paths across repo
boundaries are the hazard; `git -C` or an absolute path is the fix.

---

## OUTCOME — SEAT_QUESTION halt (second one, again correct) → RULING S, amendment #9

The resumed implementer built nothing and halted: mid-sweep it measured **ruling R's load-bearing
absence claim FALSE** against a live free cube, and refused to write a gated note embedding a premise
it had just disproved. Tree clean at `8cc5d72`, `git status --porcelain` empty, suites 191+396, and
it left the died-run17 scratchpad partial untouched. Its own framing of why it stopped is the
standard this arc wants: the cube sits INSIDE its title-selected pool AND inside its 16-cube
maintainer set, so *even the mandate's required scoped verdict sentence* ("absent from the
title-selected pool") could not have been written honestly by that run.

**What it found:** **StatCan 98-10-0621-01** crosses `Primary household maintainer` ×
`Population characteristics` × `Tenure` at CMA level — because it carries immigrant status as
**MEMBERS of a `Population characteristics (46)` dimension, not as a dimension NAME**, which is
precisely what the sweep's dimension-name selection could not see. Third instance in this arc of an
absence claim being a property of the SEARCH.

**Seat re-verification, live and independent, before any ruling:** cube metadata, all member ids, the
maintainer/persons counts and the tenure leg all reproduced exactly. The universe corroborates three
ways — Québec maintainers **3,749,035** = the published private-household count already cited in
`census.py`'s T13b docstring; persons **8,308,480** vs probe P3's independently measured 8,308,475.
The seat then computed what the probe had not: the HORS_RMR province-net residual for BOTH
quantities (headship 0.5169 — matching the probe's own figure exactly — and ratio 0.9600), and the
true owner-maintainer ratio, which showed the person-weighted proxy OVERSTATES it everywhere.

**OPERATOR RULED (2026-08-14) → RULING S, amendment #9, `16561e0`:** both inputs take 98-10-0621-01
on the `Before 2016` member — headship 0.5259/0.5054/0.5169, ratio 0.9634/0.8910/0.9600 — with ZERO
geography and ZERO metric transport. Ruling Q's cube becomes the coarse sibling cross-check; P4's
anchors still source the sweep span; ruling R's absence claim and its "general rate overstates"
caveat are both reversed (the settled stock measures HIGHER than the general population).

- outcome: **HALTED (SEAT_QUESTION), nothing built, no fix rounds — correct for the second time.**
  Superseded by run 18, a FRESH successor (a halt has no resume, and run 17's own orientation block
  is stale against post-#9 bytes).
- `ADVISOR RULING FIRED @p8-second-halt` — cost: transcript-scale proxy, full forward at ~470k.
  Catches adopted: partially refute my own earlier Task-26 routing rather than silently superseding
  it (the METRIC direction I had called unmeasurable is measured); frame the member choice as
  COHERENT across both quantities rather than per-quantity; layer the sources explicitly
  (measured > sibling-measured > borrowed); and run the member-level sweep on seat authority with a
  committed cache rather than asking for it.
- `ADVISOR RATIFY FIRED @amendment-9` — caught four sentence-level defects in the seat's own
  amendment text before commit: a claimed count reproduction the arc's own probe contradicts
  (156 vs 175, selection-rule dependent); a floor gate silently mixing cubes and members; a sibling
  cross-check overclaiming like-for-like agreement across two differing axes; and r5-F4's
  now-falsified "province-net residual is not cheaply available" parenthetical left unsuperseded.
