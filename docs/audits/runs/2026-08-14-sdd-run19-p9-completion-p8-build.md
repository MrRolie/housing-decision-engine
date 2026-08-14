# Seat-run dispatch record — run 19 (P9 completion, then P8 build)

Successor to run 18, whose task 1 halted fork-class and whose task 2 never started. A fix/halt has
no resume: fresh dispatch, with the ground now settled by ruling T (amendment #10).

- date: 2026-08-14
- script: `mm-spine/.claude/workflows/mm-sdd-pipeline.js` sha256
  `d7743e42b0ebe6499f8f5af986b471ea3417aff067710048dc39aa8756e315ea` @ mm-spine `f4d7cca`
- args: `2026-08-14-sdd-run19-p9-completion-p8-build.args.json` (sha256
  `99ce6a102f374cf3cc4d13269e21c9517766e21db63253c1dd2c29ebcdf7dfa6`)
- models: opus/opus; load_bearing ×2; money_path: false ×2; WAVE-0 vacuous
- preconditions (GROUND FIRST, seat's own run): HEAD `25a3d88`, `./scripts/test-all.sh` green at
  hde 191 + demoflow **398** (the +2 over 396 are P9's own glob contract gates on the untracked
  probe), `test_probe_contracts.py` 22 passed, checkout free. Tree carries two untracked inherited
  files by design: `probes/run_p9.py` (complete, working) and `tests/test_probe_p9.py.parked`
  (correctly NOT collected).

## What this run finishes

**P9 completion.** Run 18 measured the whole closure and deliberately wrote none of it, because it
had just found a source that changed the ruling. The measurements stand — the mandate says DERIVE
FROM THE CACHED PULL and re-pull only on a digest mismatch against
`ca18fcc7444ec5ec4de1fc01bd600f4c2bb0d86d83c55423009fa5b5cd46ff7a`, saving ~20 minutes, with the
explicit instruction that a changed catalogue is a fact to publish rather than an error, and that
run 18's numbers must never be republished under a digest that does not match them.

Three specific completions: the committed index (compact derived, not the 5.29 GB raw dump) with its
pins rows and regen-equality gate — **which is what converts "the search is closed" from a session
measurement into a claim**; the restored `.parked` gate suite, run against the completed artifact
with any failure reported rather than loosened; and the correction of the implementer's own flagged
docstring defect (cache estimated at ~400 MB against a measured 5.29 GB — the depth-1 class, caught
by the agent against itself).

The verdict is scoped by mandate: closed at MEMBER level over the full catalogue as of the recorded
vintage and sha, with the residual NAMED and the vocabularies PRINTED so a reader can judge them.
The direct fork-class result gets its own line — exactly four cubes in 8,226 carry a household-
maintainer dimension with any immigrant vocabulary — as does the positive control, since the two
cubes previous searches missed both landing in the flagged class is what makes the instrument's
sensitivity a measurement rather than a hope.

**P8 build.** The note that three runs have now deferred, written once on settled ground, carrying
both inputs under rulings S and T. Its load-bearing check is ruling T's **quantified territory
gate**: the 1:1 claims are verified by population comparison against `pop-as-ra-base.xlsx` with the
delta reported as a Fact, and a gap above 1% HALTS rather than being footnoted. It must also show
the >1 ratio as COMPOSITION from its own printed propensities (island non-immigrant 0.4210 vs
immigrant 0.4529) and distinguish it from the pooled-ratio anti-pattern — asserting the composition
without printing the numbers that establish it is precisely the depth-3 defect this arc grades.

## Advisor discipline

- `ADVISOR RULING SKIPPED @run-19 dispatch — no new ruling. Both tasks execute rulings S and T
  verbatim plus the four requirements already adopted from the @p9-halt-disposition FIRED call
  (artifact-pending phrasing, composition framing, cited-not-borrowed flag, quantified territory
  gate). The standing probe discipline is cited from the charter, not re-decided.`

- run id: `wf_d4cb7125-576` (dispatched 2026-08-14; task id wz0ssltzu)
- outcome: (appended at run close)

## Fix-agent death and resume (2026-08-14, second API death of the session)

The P9 implementer and reviewer both COMPLETED; the fix agent died on `API Error: Connection lost
mid-response`. Task 2 (P8 build) never started. Resumed under the SAME run id, args unchanged: the
implementer and reviewer replay from cache and only the fix round re-runs. Verified before resuming
that the dying agent applied NOTHING — all three cited sites are still unfixed — so the resumed fix
starts from the state its own mandate describes.

- resumed: 2026-08-14 (task id wgc4mxe3r, same run id `wf_d4cb7125-576`)

## What the review established before the death (the load-bearing half is DONE)

Verified INDEPENDENTLY, by re-deriving P9 from run 18's real 5.29 GB cache in-process with DATA_DIR
and OUT redirected into scratchpad so the tree was never written:
- the canonical raw sha256 **reproduces** `ca18fcc7444ec5ec4de1fc01bd600f4c2bb0d86d83c55423009fa5b5cd46ff7a`
  — equal to run 18's recorded value AND to the new `pins.RAW_SOURCE_SHA256` row;
- the committed **index regenerates BYTE-IDENTICAL**, and so does the committed **note** — so the
  note is genuinely generated and the derivation genuinely clock-free;
- class counts 878 / 9 / 1,660 / 5,679 sum to 8,226; the four-cube maintainer cross re-derives from
  the committed listing independently of the header field; 24 flagged cubes reach CMA;
- **the gate suite was restored WITHOUT loosening** — diffed against the recovered `.parked`
  original (sha 4bd12d67…), the change is ADDITIONS ONLY: four new gates plus one docstring edit,
  no assertion weakened, and `assert "no such source exists" not in note` unchanged, so the live
  catch it made was fixed at the PRODUCER rather than at the gate;
- **fixture fidelity proven, not assumed**: all six fixture cubes are byte-identical to their
  canonical lines in the real 8,226-cube pull, so the floor-guard battery and regen gate run against
  data StatCan actually published;
- footprint clean: `pins.py` is +29/-0, three dict entries with comments and no logic touched; no
  stray files; `git check-ignore` confirms none of the nine new paths is gitignored, so the commit
  cannot silently drop the fixture or the index.

Suites 191 + **426** on the seat's own run.

## The one finding, and why it is worth the round

MED, and pointed: **three more hand-typed figures the run's own measurement contradicts survive in
`run_p9.py`** — `:354` "a 16-minute run", `:1008` the user-facing `--help` string "(~16 min)", and
`:626` "a 400 MB index is not an index" — against the measured 1,211 s (20.2 min) and 5.29 GB. This
is the depth-1 class the task was chartered to close, left behind by the same commit that closed the
docstring instance, and `:626` reuses the exact stale 400 MB figure in a new rhetorical role. Two
sites (`:81`, `:369`) were already corrected in the measured form, which is what makes the survivors
a slip rather than a policy. The reviewer specified the fix text; the resumed round applies it.

Two report-accuracy items the reviewer checked and cleared without a fix: a stale note-sha in the
determinism evidence (superseded by its own byte-identical regen of the FINAL bytes), and a
mutation-outcome claim that did not reproduce under the reviewer's own widening — the discriminating
instrument for that class is the synthetic `maintainer_only_as_member` case, and it works.

## Carries recorded from the review (none blocking)

- `human_bytes` formats the measured `cache_bytes` into the note's "5.29 GB" and is UNGATED — a
  mis-scaling mutation reds nothing, because the note is never regenerated in-suite (only the index
  is). The regen-equality property covers bytes, not formatters.
- The redundant `.replace("\xa0", " ")` in `normalize` is non-discriminating: `str.split()` already
  treats NBSP as whitespace, so deleting it leaves its gate green. The gate pins the OUTPUT
  correctly but not the clause the note calls out as "not hypothetical".
- **Serialization is duplicated across the gate boundary:** `test_probe_p9.py::_render` restates
  `write_index`'s exact `json.dumps` call, so the regen gate compares what `_render` emits rather
  than what `write_index` emits — a change to `write_index`'s serialization alone would leave it
  green. Identical today (verified); the pins row + digest-triple gate would catch it on the next
  regeneration through that path.
- **`product_id()` normalization is ONE-SIDED**: it normalizes the `getCubeMetadata` (string) side
  only; the catalogue side is read raw at four sites. If `getAllCubesListLite` ever re-types to
  string the vacuous-disjointness returns — but it fails CLOSED (the positive-control membership
  test refuses), and the fixture's mixed typing is pinned so the asymmetry cannot silently vanish.
- `RAW_SOURCE_MEMBER["catalogue_member_index_p9.json"]` is a prose description of an OPERATION
  rather than a member name, and the P9 producer writes its own provenance string instead of calling
  `raw_member()` — a recorded deviation from the P2 precedent it cites, with both registry gates
  still holding.
