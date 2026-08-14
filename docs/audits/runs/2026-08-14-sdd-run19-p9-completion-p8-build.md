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

- run id: (appended at dispatch)
- outcome: (appended at run close)
