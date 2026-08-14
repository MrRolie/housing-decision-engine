# Seat-run dispatch record — run 18 (P9 catalogue closure, then P8 build)

Successor to run 17, which halted correctly on refuting ruling R. Fresh dispatch: a halt has no
resume, and run 17's orientation block is stale against the post-amendment-#9 spec bytes.

- date: 2026-08-14
- script: `mm-spine/.claude/workflows/mm-sdd-pipeline.js` sha256
  `d7743e42b0ebe6499f8f5af986b471ea3417aff067710048dc39aa8756e315ea` @ mm-spine `f4d7cca`
- args: `2026-08-14-sdd-run18-p9-closure-p8-build.args.json` (sha256
  `abe4105945dbc0715693f5642d8bd222aaa17a1554e22d3197a039b4b02223dd`)
- models: opus/opus; load_bearing ×2; money_path: false ×2; WAVE-0 vacuous
- preconditions (GROUND FIRST, seat's own run): tree clean at HEAD `940df83`,
  `./scripts/test-all.sh` green at hde 191 + demoflow 396, checkout free

## Why the order is P9 first

Three absence claims in this arc have been refuted by a cube a selection rule could not see —
ruling F (HEAD-vs-GET on guessed slugs), ruling Q (a 98\*-family + title-tier scope), ruling S
(dimension-NAME selection). Writing P8's note before closing that class would risk a fourth
amendment to a note that claims to be generated on settled ground. So **P9 closes the search first,
by not selecting at all**, and P8's note then carries P9's closure verdict by reference.

P9's design, in one line: pull `getCubeMetadata` for the ENTIRE catalogue (~8,206 cubes, no title
pre-selection), match two vocabularies against **dimension names AND every member name**, and single
out the class both missed cubes fell into — matching both vocabularies where at least one match is
MEMBER-only. The closure is made reproducible rather than a session memory by committing a COMPACT
derived index (not the raw dump) carrying the catalogue count, cube-list vintage, sha256 of the full
raw pull, the exact vocabularies used, and the run date — pinned the way this repo pins its other
committed artifacts, with the regen-equality gate.

The residual is named rather than hidden: member-level closure does not close a cube whose axis uses
vocabulary outside the two lists (the lists are printed IN the note so a reader can judge them), nor
anything outside StatCan WDS. And if P9 surfaces a BETTER source than ruling S's, that is fork-class
— SEAT_QUESTION and stop, not a quiet amendment.

## Seat authority note

The sweep was decided by the seat, not asked of the operator: it is method, not a fork, and three
misses make it obviously right. Reported rather than escalated.

## Advisor discipline

- `ADVISOR RULING SKIPPED @run-18 dispatch — no new ruling. Task 1 is method under seat authority
  (the closure sweep); task 2 executes ruling S verbatim. Both cite the standing probe discipline
  (charter §Probe discipline) and the post-#9 spec bytes by name. The two FIRED calls that shaped
  this run — @p8-second-halt and @amendment-9 — are recorded in run 17's record.`

## Carries for Task 25b (current as of ruling S; supersedes run 16's block)

1. Ratio 0.9634 / 0.8910 / 0.9600 and headship 0.5259 / 0.5054 / 0.5169, `Before 2016` member,
   98-10-0621-01; RA members borrow parent CMA; HORS_RMR is the computed province-net residual.
2. `ImmigrantInputs` needs PER-FIELD provenance — under S both MTL quantities are cited (flag None
   for that member), while RA members and HORS_RMR carry different provenance per field.
3. **HORS_RMR's flag needs a seat ruling at 25b dispatch:** a value COMPUTED as a residual from
   cited counts is not `borrowed_prior`. Either flag None with the residual method stated in
   provenance, or mint a new `ANCHOR_FLAGS` member — which `constants.py` deliberately makes land
   loudly (import-time raise) rather than silently. Decide it in the mandate, not at the
   implementer's discretion.
4. Delete `CENTRAL_ASSUMPTIONS["immigrant_ratio_center"]` and its `SWEEP_GRID` twin in ONE edit (the
   keyset-equality test binds them). Per-geography values live in the join table as cited Anchors;
   Task 29's sweep perturbs the ratio via a uniform join-table override spanning [0.155, 1.033],
   still sourced from `CONSTANTS["immigrant_ownership_ratio_sweep_span"]`.
5. `constants.py`'s q_live comment "today the ONLY key read from this dict" is stale as of run 15.
6. From run 15: make `formation.py`'s i2 forward reference true and DELETE its caveat; the immigrant
   leg asserts nothing (negative arrivals → negative owner households); the new cohort/demand →
   loaders import direction has no gate.

- run id: `wf_0b36b300-bc8` (dispatched 2026-08-14; task id w6qrhywum)
- outcome: (appended at run close)
