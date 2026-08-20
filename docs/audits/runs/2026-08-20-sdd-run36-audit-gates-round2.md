# Seat-run dispatch record — run 36 (audit gates, ROUND 2, on the folded bytes)

- date: 2026-08-20
- **shape: custom fan-out, not the sdd prefab** — audits are read-only, so the prefab's
  implement → review → fix shape does not fit. Three gates in PARALLEL via `agent(…, {agentType})`,
  then a COMPLETENESS CRITIC on their union.
- script: `2026-08-20-sdd-run36-audit-gates-round2.script.js`, committed beside this record, sha256
  `dde573131bed1637732a9bba918787f734363c2075ff96b9de9a481daf4874c0`. **The script IS the args**, so it is committed to keep the arc's reproducibility convention.
- agent types: `mm-spine:quant-financial-engineer`, `mm-spine:stress-tester`,
  `mm-spine:data-integrity-validator`, plus a general completeness critic
- preconditions, DERIVED from the seat's own run: code tree as of `6784c03`, hde **191** +
  demoflow **1167**, tree clean

## Why round 2 exists at all

Each plan gate's own Step 5 says re-dispatch once if DECISION-CRITICAL folds happened. They did:
round 1's CRITICAL (a one-of-five-axis `rank_stable` attestation) and its HIGH (the banded-curve
artifact) are both now BUILT OUT, across five substantive commits — `98c2f10`, `f5106aa`, `c83595e`,
`16fc229`, `8c8e0f0`. **The gates are being re-aimed at code that did not exist when they last ran.**

## The dry test is the deliverable, not the findings

**A round is DRY when it produces only REFUTED or DERIVATIVE findings.** The mandate tells each gate
that restating a ledger ruling is derivative and that its budget belongs to what the ledger does not
cover. It also hands each gate an explicit **CONFIRMED-SOUND list** — ruling U's presence bar, the
six cohort oracles, the curve's per-member closure, the reduced-sweep fail-safe, and the
ownership-floor tripwire's proven fire on the run-15 class — **so no round-2 token is spent
re-establishing what round 1 and the folds already settled.**

**The completeness critic is the part that decides whether to stop looping.** Its brief is explicitly
NOT to audit: it reads the three `coverage_note` fields, asks which modality was never run, which
load-bearing claim remains unverified by anyone across both rounds, which surface went unread, and
whether the ROUND is dry. **It is told that a recommendation to STOP is a valid and valuable
output** — an audit loop that cannot terminate is its own defect, and this arc's default pressure is
DELETE.

## The seam class is handed forward as a question, not a checklist

Three producer/contract seams were found and fixed (the 64-vs-16 hash width, `check_registry`'s
self-rejected record, and the `malformed_band` non-finite endpoint), and a generalized property now
asserts that every record a producer can emit validates against its contract validator. **Round 1 was
told to find the third and did. Round 2 is asked to find a fourth OR to establish that the
generalized property closes the class.**

## Named deliverable: amendment #12's stale QFE legs

The quant gate returns the re-measurement in a dedicated `remeasurement` schema field. Amendment
#12's legs (0.195–0.337% / 0.96–1.65% / 30×–200× / equality at |ED| ≈ 19–21%/yr) were measured
against the RETIRED banded curve and the tree now advertises them as STALE. Round 34 already measured
one input — the sub-25 gross positive gain the floor discards moves 23.0–25.9k → 17.6–20.5k (−23%)
and its character inverts from coarsening artifact to genuine formation mass.

## Two open seat items are handed to the gates rather than argued internally

- **26.1% (in `formation.py`) vs 26.72% (in the run-34 record AND the seat's report to the
  operator)** for MTL_RMR fc concentration — unreconciled, likely a pooling convention. The quant
  gate is asked to settle it.
- **The 2026–2029 negative D_native window** straddles the `p`→`proj` vintage seam and round 1 could
  not separate cohort geometry from junction geometry. Quant and data are both pointed at it.

## The hardlink hazard is in the preamble, not just the ledger

Round 1's 35a reviewer truncated a venv `.pth` file HARDLINKED to the shared uv archive cache —
outside the worktree. The round-2 preamble carries the lesson as a binding instruction: **"footprint:
demoflow/** only" is a GIT-TRACKED-PATH rule, and copying is not enough if you copy by writing
THROUGH a hardlink.** Break the link first, or use `cp --remove-destination`.

- run id: (appended at dispatch)
- outcome: (appended at run close)
