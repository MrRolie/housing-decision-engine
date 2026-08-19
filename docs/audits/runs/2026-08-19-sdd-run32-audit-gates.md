# Seat-run dispatch record — run 32 (the three pre-PR audit gates)

- date: 2026-08-19
- **shape: NOT the sdd prefab.** These are read-only AUDITS, not implementation tasks, so the
  prefab's implement → review → fix shape does not fit. This run is a custom fan-out: three
  independent gates in PARALLEL via `agent(..., {agentType})`, which keeps the work inside the
  sanctioned workflow lane while using the specialist agent types the plan names.
- script: `2026-08-19-sdd-run32-audit-gates.script.js`, committed beside this record, sha256
  `ee130838da79250635a61b12f4486bb213a6d1d2ecc76facbdf1e20ecec3a62a`. **There is no args.json — the script IS the args**, so it is committed to keep the arc's
  reproducibility convention from lapsing just because the shape changed.
- agent types: `mm-spine:quant-financial-engineer`, `mm-spine:stress-tester`,
  `mm-spine:data-integrity-validator`
- preconditions, DERIVED from the seat's own gate run: code tree as of `aaf8e1f`, hde **191** +
  demoflow **1097**, tree clean

## The gates were MIS-AIMED in the plan, and that is why they are re-framed here

All three plan tasks say "audit everything in *this plan*, against the implemented code" and list the
plan FIRST among the reads. **The plan is no longer the governing description of this system** — the
spec has since taken amendments #7–#16 and rulings A–U, several of which refuted plan premises
outright. An auditor pointed at the plan would grade correct code against superseded requirements and
report drift where the tree is RIGHT and the plan is WRONG. Every gate now gets: the SPEC governs;
the plan is historical; classify each divergence as plan-superseded / code-defect / genuine-drift;
the ruling ledger and run records are INPUTS, and a finding that restates a recorded ruling is
DERIVATIVE.

**Task 32's own dispatch could not have fired.** Plan Task 31 writes
`subagent_type: mm-spine:quant-financial-engineer` and warns in-line that "a bare name fails to
resolve"; Task 33 uses the prefix; **Task 32 writes `stress-tester` BARE.** The gate that hunts for
guards that cannot fire could not itself have fired. Fixed here.

## What the seat handed them that the plan could not

The plan predates the findings. Each gate carries named targets from the ledger: the aligned-ρ
operand question (dead code until run 30 wired it — does consuming it move ED's sign or the ranking
order?); the band-entry construction that replaced the uncited `* 0.1`; the one-sided suppression
envelope (`±2.5 × n_cells` centres a `--` cell's [0,5] interval on a contributed 0, but suppression
can only ADD); the unpinned `NULLABLE_REASONS` set; and **ruling U's presence-bar inference**, handed
to the data gate as the single most valuable thing it could refute.

**A seam class is named and the gates are told to find the third instance.** Two producer/contract
pairs have disagreed while staying green because no test crossed them — the 64-vs-16 assumptions-hash
width, and `check_registry` emitting a record its own validator rejected. Both fixed.

## Advisor discipline

- `ADVISOR RATIFY FIRED @run-32 dispatch — gate fan-out shape + schema seam.`

The advisor ratified the fan-out (and said not to add verify stages: **the seat is the verify
stage**) and caught four things, one of which is the seam class **inside the seat's own dispatch**:
the preamble told gates to classify into "exactly one of" THREE classes while the schema enum carried
FOUR — `spec-gap` existed in the contract and nowhere in the prose, and the schema forced the field
on findings that are not divergences at all. Two committed vocabularies, one wider, green because
nothing crossed them. Now defined explicitly. Also adopted: `decision_critical` made REQUIRED (the
one field the plan's original framing demanded, and optional fields get omitted); an explicit
CONCURRENCY line, since this is the arc's first parallel execution in the live checkout and three
simultaneous suite runs in one venv is contention plus wasted minutes; and the HEAD pin rephrased as
CODE-STATE, because committing this very record moves HEAD before any gate reads the tree.

## Fold discipline, pre-stated so a round-1 green cannot quietly become "gates done"

1. The seat REPRODUCES every CRITICAL and HIGH before folding it.
2. **A missing gate is NOT RUN** — re-dispatch it; never grade on 2 of 3.
3. Surviving decision-critical findings become a PIPELINE run, because fixes are mutations and get
   the commit-nothing / review shape rather than in-lane patching.
4. Then re-dispatch THAT gate once on the folded bytes — the plan's own Step 5, and the
   loop-until-dry ethos: a round is dry when it yields only refuted or derivative findings.
5. The seat writes the three audit documents at the plan's paths; **the gates return verdicts only
   and write nothing.**

- run id: (appended at dispatch)
- outcome: (appended at run close)
