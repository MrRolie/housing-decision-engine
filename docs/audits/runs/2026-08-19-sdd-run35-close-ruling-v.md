# Seat-run dispatch record — run 35 (close operator ruling V)

- date: 2026-08-19
- script: `mm-spine/.claude/workflows/mm-sdd-pipeline.js` sha256
  `d7743e42b0ebe6499f8f5af986b471ea3417aff067710048dc39aa8756e315ea`
- args: `2026-08-19-sdd-run35-close-ruling-v.args.json` (sha256
  `db122783f5cd5283a9206d39523bc0da56f1a665877a16accc1461cddb3e0928`)
- models: opus/opus; load_bearing ×2; money_path: false
- preconditions, DERIVED from the seat's own run at `c83595e`: hde **191** + demoflow **1160 passed,
  2 failed** — the two `test_golden.py` diff tests, **RED BY DESIGN** until task 2 re-mints

## Why this is a successor rather than a resume

Run 34's task 34a returned FINDINGS, and the pipeline halts on that verdict, so task 34b — the golden
re-mint — never started. The seat fixed the single LOW itself at fold (a comment mislabel) and
committed the curve, so this run picks up the deferred half against a landed curve.

## The task order is load-bearing and it is the run-31 lesson applied honestly

Task 1 rewrites artifact provenance prose, which **moves the headship artifact's digest**; task 2
mints the golden once. Reversed, the golden is minted twice and the second mint hides the first. Note
the distinction from run 31, where the seat asserted an ordering rationale the reviewer then measured
FALSE: here the coupling is direct and mechanical — the note text is inside the artifact, so editing
it changes the digest that the envelope carries. That is a measurement, not a precaution.

## The binding instruction of this run, and it is a process lesson not a code one

**The reopening trigger must be MECHANICALLY CHECKABLE.** Run 15's record wrote "it reopens when
Task 29 lands an age-resolved headship curve"; Task 29 landed WITHOUT one, nothing reopened, and the
defect survived three further review rounds until the pre-PR gate caught it. **A condition whose
trigger nobody checks is not a condition.** So the sub-25 ownership question's reopening language must
name a checkable artifact field or a test that FIRES — and if it cannot fire mechanically, the note
must say so rather than reading like a guarantee.

## The seat corrects its own record in this mandate

The 14-18% concentration acceptance metric was the seat's, taken from the design panel's explicitly
PROBE-GRADE figures and written into a mandate as if it were measurement. The run-34 reviewer could
not reproduce the seat's own quoted baseline under any convention. The mandate therefore forbids the
tree from recording 14-18% as a met-or-missed gate, and requires it to record instead: the collapse
is measured (79.81% → 26.72%, HHI 0.6585 → 0.1763), the band is convention-dependent, and the
residual peak at **age 26 is the ownership lattice's entry step** — the next ordered step.

Also carried: the under-15 zero must be written as a POSITIVE BOUND (`X ≤ 35` households against
1,364,340 persons, below 2.6e-5), never as "the table is silent" and never as "proved exactly zero" —
and the implementer must verify that arithmetic itself.

- run id: `wf_d6e1c5d6-ca2` (task `wahcdivpd`)
- outcome: **APPROVE ×2, 0 unresolved** (fix rounds 2 / 3); 15 agents, 1,856,007 subagent tokens.
  Landed `16fc229` (note discharges) and `8c8e0f0` (the single mint).

## Outcome — RULING V IS CLOSED. Gate: hde **191** / demoflow **1167** / both suites passed.

**THE RUN-15 FAILURE CLASS IS NOW CAUGHT, AND THE CATCH WAS PROVEN AGAINST THAT EXACT CLASS.** The
reviewer's M6 mutant is the whole point of this run: a **CONSISTENT** downward extension of the
ownership lattice — moving `census._AGE_BAND_SPEC` and `formation.OWNERSHIP_LATTICE_FLOOR` together,
which is precisely the quiet self-consistent edit a soft condition cannot see — **REDS the tripwire
with amendment #12's re-measurement obligation verbatim in the message, while both twin pins stay
GREEN.** `_AGE_BANDS` derives from `_AGE_BAND_SPEC`, so no spec move can hide from it. Run 15's
"it reopens when Task 29 lands an age-resolved headship curve" is now a test rather than a hope.

**Final ranked order, fully re-ordered, every mean ED positive** (HORS_RMR −0.000290 → +0.001102, the
predicted sign flip): LANAUDIERE 1, LAVAL 2, LAURENTIDES 3, HORS_RMR 4, MTL_RMR 5, MONTEREGIE 6,
QC_RMR 7, MTL_ISLAND 8. `rank_stable` false on every row — run 33's five-axis verdict is unchanged by
this curve. `assumptions_hash` f39a8a24 → 9a876ab5; 13 sources; `exclusions` empty.

## A SELF-DISCLOSED ENVELOPE BRUSH, and the disclosure is the point

Building its probe copy, the 35a reviewer's `printf >` truncated
`demoflow/.venv/.../_editable_impl_demoflow.pth` **in place** — a file HARDLINKED to
`~/.cache/uv/archive-v0/.../_editable_impl_demoflow.pth`, i.e. **outside the worktree and shared with
every other environment built from that uv archive entry.** It restored immediately (broke the link on
the copy side first, then rewrote the original 82 bytes) and verified three ways: `cat` on both links,
`find -inum` showing only the worktree venv and the archive entry, and both venvs resolving
`demoflow.__file__` to their own src. No git-tracked file was touched.

**Recorded because it generalizes and the footprint rule did not cover it:** "footprint: demoflow/**
only" is stated in every mandate as a GIT-tracked-path rule, and a hardlinked venv file inside
`demoflow/**` reaches OUTSIDE the repo entirely. **Probing on a copy is not sufficient when the copy
is made by writing through a hardlink.** Candidate mm-spine harvest.

## Carries

- **26.1% (tree) vs 26.72% (run-34 record) for MTL_RMR fc is UNRECONCILED**, and the seat's own record
  and its report to the operator both carry 26.72%. Both figures pre-date this run and it carried
  neither: the implementer correctly declined to transcribe the record's number into the tree. The
  record's value sits inside the tree's own stated per-year range (24.3-40.4%), so a pooling-convention
  difference is the likely reconciliation. **79.9 vs 79.81 rounds fine; 26.1 vs 26.72 does not.**
- **Naming a test inside the artifact note couples a test RENAME to the golden.** Renaming
  `test_the_ownership_LATTICE_FLOOR_IS_A_TRIPWIRE...` now changes `headship_by_age.json`'s bytes, hence
  `data_vintage`, hence both goldens — and it would fail as "the DATA moved" when no data moved. A
  consequence of this package's deliberate notes-ride-the-digest design, not a defect.
- **Nothing mechanically pins `formation.py`'s corrected acceptance-metric prose.** All three
  statements are present and correct, but nothing reds if they regress — and run 34 caught a false
  claim in this exact block. The new tests establish that reading source text off disk is in-idiom
  here, so pinning "IS NOT A GATE THIS CURVE MET OR MISSED" is cheap.
- **The tripwire's failure message is only partially pinned** — the `pytest.raises(match=...)` catches
  "ownership lattice floor MOVED" but not the amendment-#12 obligation text the note advertises it as
  carrying, so that sentence could be stripped with both gates green. One-token widening closes it.
- `_zero_support_note`'s bound renders with `{rate_bound:.1e}` and then asserts the rate is "below" it;
  round-half-even means a future vintage could round DOWN and make "below" false. Pre-existing,
  unchanged, and true today (2.5653e-5 < 2.6e-5).
