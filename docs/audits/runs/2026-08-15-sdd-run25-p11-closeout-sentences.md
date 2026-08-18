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

---

## OUTCOME — 2/2 APPROVE, verify PASS → LANDED `3c15927` (P10) + `4ed39a3` (P11 + sentences)

11 agents, 0 errors. P11 closeout APPROVE (2 fix rounds), sentence corrections APPROVE (1). Suites
**191 + 734**, three green runs with outbound network hard-blocked, no flake. Tree clean, pushed.

**The closeout verified against FIRST SOURCES, not against the producer.** All 272 extract cells
match the stood-down instance's independent pull with ZERO value differences and identical withheld
sets; every ρ figure was recomputed with its own CSV reader and its own remap, importing neither
`census.py` nor `hors_aligned.py`, and reproduces exactly (served spread 1.202409 pp, **bound spread
1.212115 pp** — the adverse structure holds at both corners). External anchors hold and do not
co-move. Extract sha matches its pins row; the generator reproduces the artifact byte-identically;
two independent pulls minutes apart are byte-identical at 84,049 bytes.

**The scope fence was PROVED, not asserted:** re-running `derive_ownership_from_csv` after the
`census.py` seam refactor reproduces the committed ownership artifact with zero geography × band
values moved and identical serialized size; shipped HORS_RMR unchanged; the aligned artifact carries
only HORS_RMR; `load_ownership_rates` not re-pointed; zero `_MAINTAINER_TOTAL_MEMBER` references
remain.

**The sub-floor correction gained something the mandate did not ask for and should have:** besides
pinning that the extract DOES publish sub-25 counts, there is now a test that makes the clause
**RETIRE ITSELF LOUDLY when the ownership lattice is extended** — so §7's ordering constraint
(age-resolved headship first, then the floor) cannot be violated quietly by a future task.

### Honest disclosures the closeout made rather than smoothed

- **No WDS call was made this run.** The 272-cell reproduction reuses the stood-down instance's
  preserved pull (mandate-sanctioned), and the 98-10-0003-01 membership is verified against the
  extract's recorded `_pull.membership` block and P10's note, **not re-derived live**.
- The unpublished-remainder bound is called an upper bound "by construction" at three sites; under
  independent round-to-5 per cell that is LOOSE rather than exact — two committed fields carry a
  NEGATIVE remainder (published band cells exceeding the published all-ages cell), which is why the
  clamp exists. Disclosed adjacent, magnitude immaterial (single-digit households against a
  12,675-household subtraction), and the remainder also absorbs the un-pulled under-25 maintainer
  member, so it over-covers.
- `hors_aligned` reaches through to `census._band_counts`, `._PROVINCE`, `._QC_CMAS` and
  `._AGE_BAND_SPEC` despite the public-seam refactor introduced for it — the refactor's stated
  rationale covers only part of the reach-through.
- Two weak assertions recorded: `assert "5" in rounding["note"]` is satisfied by almost any prose,
  and a two-cell floor under a 12,675-household quantity. `relative_delta_bound_pct` is emitted into
  every band's provenance row and asserted nowhere.

### ⚠ THREE DISPATCH-CONTEXT ERRORS — in the seat's brief, not in the work

- **X-1, the serious one: "Committed HEAD is 34fd60a" names an object that has NEVER EXISTED in this
  repo** (`git cat-file -t` → `Not a valid object name`; the actual HEAD was `23c64eb`). A
  hand-typed identifier the tree contradicts — the seat's signature failure class, now its FOURTH
  instance this session after two suite counts and the §6 person-weight/conversion pair.
- X-2: "demoflow 696" cannot be reproduced, because it was measured on a dispatch-time tree state
  that was never committed; the gate is 734, fully attributed from a measured 604 HEAD baseline.
- X-3: the `MM_PORTFOLIO_DATA_DIR` hermetic-env instruction has no referent in this repo — inherited
  from a template and never checked.

**MECHANISM CHANGE, since care has now failed four times:** every identifier and figure in a dispatch
context is DERIVED at authoring time — `git rev-parse --short HEAD` and a live suite run piped into
the args — never typed. The same fix already applied to commit messages; it now applies to briefs.
X-3 adds a second rule: an inherited instruction must have a referent verified in THIS repo before it
rides in a mandate.

- outcome: **2/2 APPROVE / landed `3c15927` + `4ed39a3` / suites 191+734.** Next: the seat writes
  amendment #13 (the values are now REVIEWED), then a run regenerates P8 and updates the join table
  where the citation coupling reds and then greens, then Task 27.
