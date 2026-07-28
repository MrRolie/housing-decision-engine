# T1 WDS-extraction stress audit — `e043500..896d5c0`

Worktree `housing-decision-engine.demoflow-t1`, branch `feat/demoflow-tranche1`.
Commits under review: `f0b6736` (extraction) + `896d5c0` (gate fixes).
Tier: STANDARD (diff + immediate callers + relevant tests).
Written incrementally during the run.

## Baseline

- `cd demoflow && uv run --extra dev pytest -q` -> **38 passed in 0.19s** (no network hit
  in the offline suite).
- Live WDS reachable from this box: `POST getCubeMetadata [{"productId":98100001}]` -> 200.
  So live old-vs-new replay is available, not just analytical.

## Reopen criterion (restated)

(a) rewire CHANGED observable behavior — note bytes, wire behavior, probe verdict; or
(b) a gate CLAIMED load-bearing is proven VACUOUS.
Everything else -> CARRY.

## Probe log

### PROBE 1 — is the golden fixture a tautology? (attacks the gate's own claim)

`test_probes_common.py` docstring: the fixture "was pinned from the PRE-extraction
`_provenance_header()` of each probe — so this is an old-vs-new equivalence check, not a
self-consistency one." Falsifiable; falsified it would be REOPEN(b).

- `git diff --stat f0b6736..896d5c0` -> the fixture is **NOT** in the fix commit, even though
  `896d5c0` introduced `_WRITTEN_BY` and changed the `written_by=` argument. Code was held to
  the fixture, not the reverse.
- Independent regeneration: `scratchpad/probe_golden_provenance.py` loads
  `git show e043500:demoflow/probes/run_p{3,4,5}.py` and calls each OLD `_provenance_header()`
  over the 4 pinned mixes, comparing list-for-list to `golden_headers.json`.

```
p3/empty: MATCH   p3/all_derived: MATCH   p3/mixed: MATCH   p3/all_cited: MATCH
p4/...   MATCH x4          p5/...   MATCH x4          FAILS: 0
```

**VERDICT: the claim holds. 12/12 golden cells reproduce from pre-extraction code.** The
4 mixes also give full branch coverage of `provenance_header` (`if log.facts:` both ways,
`if cited:` both ways).

### PROBE 2 — live record/replay old-vs-new note bytes (limb (a), the strong leg)

`scratchpad/replay_equiv.py`: monkeypatch `urllib.request.urlopen`; run the **NEW** probe
against the LIVE source while recording every response keyed on (url, method, body); then run
the **PRE-extraction** module with the same tape replayed. Both modules therefore see
byte-identical responses, so data-vintage drift is removed as a confounder. `OUT` redirected
to scratchpad in both.

```
NEW p5: wrote ... ; tape 2 entries   OLD p5: tape misses=0   RESULT p5: BYTE-IDENTICAL (9039 chars)
NEW p4: ...                          OLD p4: tape misses=0   RESULT p4: BYTE-IDENTICAL (16587 chars)
NEW p3: ...                          OLD p3: tape misses=0   RESULT p3: BYTE-IDENTICAL (22187 chars)
```

This covers **p3**, whose rewired `main()` is executed by nothing in the suite.

### PROBE 3 — ordered wire sequence old-vs-new (limb (a), wire behavior)

`scratchpad/replay_wire.py` compares the ORDERED list of
(url, method, sorted headers, body, timeout) each module issued.

```
p5: NEW 2 / OLD 2   WIRE SEQUENCE IDENTICAL   (GET,120)
p4: NEW 3 / OLD 3   WIRE SEQUENCE IDENTICAL   (GET,120) (POST,120)
p3: NEW 4 / OLD 4   WIRE SEQUENCE IDENTICAL   (GET,120) (POST,120)
```

`TIMEOUT=120` -> `WDS_TIMEOUT=120` confirmed identical on the wire; p5 keeps its own
`TIMEOUT=120` for CKAN/CSV. No extra or dropped request in either direction.

**Limb (a) is CLEAN on all three probes, verified by execution.**

### PROBE 4 — mutation battery (31 mutants: 22 KILLED, 9 SURVIVED)

Harness: `scratchpad/run_mut.sh` — exact-string mutation (fails loudly unless the anchor is
unique), full demoflow suite, `git checkout -- <the one file>`, `git status --porcelain`
verify. **Bytecode-safe**: `PYTHONDONTWRITEBYTECODE=1` + `__pycache__` purge before and after
(see finding C8 — the first pass was contaminated and inflated kill counts).

KILLED (the gate is live for what it names):

| # | mutation | killer |
|---|---|---|
| M1 | `provenance_header`: drop the blank line after written-by | 12 golden cells |
| M2 | written-by f-string -> `run_p3.py` literal | 8 golden cells (p4/p5 only — correct) |
| M3 | `if log.facts:` -> `if True:` | 3 `empty` cells |
| M4 | `if cited:` -> `if True:` | 6 `empty`+`all_derived` cells |
| M5 | `Fact.__post_init__` raise -> silent return | `test_fact_outside_a_run_raises` |
| M6 | `new_run()` returns a module-global singleton | `test_cross_probe_runs_do_not_share_a_registry` + 13 |
| M7/M8/M9 | one byte in p3 `_SCOPE` / p4 `_CITED_LABEL` / p5 `_summary` | 4 / 2 / 3 golden cells, that probe only |
| M10/M11 | p5 wrapper GET->POST; p3 wrapper POST->GET | `test_reachability_wrappers_keep_their_http_shape` |
| M12 | p5 `ok_statuses` drops 206 | same |
| M13 | `token()` loses the backtick-span branch | `test_token_parser...` + `test_p5_records_located_or_unknown` |
| M14 | `NETWORK_EXCEPTIONS` swap `SSLEOFError`->`OSError` | `test_shared_network_exceptions_did_not_widen` |
| M15-p4 / M15-p5 | CALL SITE: drop `new_run()` from `main()` | `test_cross_probe...` (+ p4 vacuous-WDS gate) |
| M24/M25/M26 | `source_reachable` drops `data` / drops `headers` / always True | `test_reachability_wrappers...` |
| M27 | drop the fresh `contextvars.Context()` wrapper from `test_fact_outside_a_run_raises` | itself — the wrapper IS load-bearing, as claimed |
| M28 | `Fact` raise-message wording drift | `test_fact_outside_a_run_raises` |
| combined | M19 (free-variable header) + M15-p5 (no `new_run()`) | `test_cross_probe...` — the gate DOES catch its named hazard |

SURVIVED (9) -> M17+M16 (C1), M20 (C2), M21 (C3), M19 (C4), M15-p3+M18 (C6), M22+M23 (C7).
C5 is not a mutant — it is a direct executable probe against `_wds.Fact`. C8 is a
methodology finding surfaced by the harness itself.


---

# FINDINGS

## REOPEN: none

Limb (a): note bytes and wire behavior are byte-identical old-vs-new on all three probes,
against live-recorded traffic replayed into the pre-extraction modules (PROBE 2/3). No probe
verdict moved.

Limb (b): every gate I mutated against its OWN named claim was KILLED, including the decisive
combined mutation (free-variable header + forgotten `new_run()`), which is the sharpest form
of the hazard `test_cross_probe_runs_do_not_share_a_registry` names. No gate claimed
load-bearing is vacuous as to what it claims.

## CARRY

### C1 [HIGH] Nothing pins that a probe's `main()` routes its header through `provenance_header`

House rule #1 ("a generated artifact may not state anything not tied to its computed state")
has NO enforcement at the call site, in ANY probe — including one that IS offline-exercised.

- **Probe (M17), the one that matters:** in `run_p5.py:585`, replace
  `header = provenance_header(facts, written_by=_WRITTEN_BY, ...)` with a hand-typed list
  literal including `"This run registered 9 provenance-tagged figures."`
  **SURVIVED — `38 passed`.** p5's `main()` is called by THREE tests
  (`test_p5_floor_guard_earns_verdict` x3 scenarios, `test_cross_probe...` x2 runs). So the
  natural reading — "p3 is the only blind spot, p4/p5 are covered by their offline runs" — is
  false: a fully hand-typed provenance header ships green through an exercised `main()`.
- **Probe (M16), the corroborating one:** the same substitution in `run_p3.py:810`.
  **SURVIVED — `38 passed`.** Explainable on its own by the disclosed p3 hole (C6); it is M17
  that shows the gap is not p3-specific.
- The reason M17 survives: `test_cross_probe_runs_do_not_share_a_registry` compares the
  *registered-count line* across two p5 runs; a constant is perfectly order-independent. The
  vacuity guard added in `896d5c0` (`_count(alone) > 0`) is satisfied by any hardcoded nonzero.
- **Why CARRY, not REOPEN(b):** the gate's *named* hazard is cross-probe registry sharing, and
  it does catch that (M6, M15-p4, M15-p5, and the combined mutation all KILLED). No gate in the
  suite *claims* to pin the call site. But this is the exact defect class the family has
  reintroduced 6+ times, and P5b/P6 are being written by copying a call block.
- **Suggested closure:** in `test_cross_probe...`, monkeypatch `_wds.provenance_header` to a
  recording sentinel and assert each probe's `main()` calls it exactly once with
  `written_by=mod._WRITTEN_BY`; or assert the printed count equals `len(log.facts)` read back
  from the module.

### C2 [HIGH] The HTTP-shape enforcement gate enumerates wrappers by NAME — a 4th probe is unguarded

- `test_probes_common.py::test_reachability_wrappers_keep_their_http_shape` names
  `t3._source_reachable`, `t4._source_reachable`, `t5._source_reachable` and nothing else
  (verified by parsing the test body: wrappers enumerated = `['3','4','5']`).
- **Live probe** (`scratchpad/probe_copypaste_trap.py`, real network):

```
LIVE getCubeMetadata  POST-parity probe -> True
LIVE getCubeMetadata  copied-from-p5 GET probe -> False
=> a p6 that copies p5's wrapper reports a HEALTHY service as unreachable: True
```

- A P6 author who copies p5's wrapper (`method="GET"`, `Range`, `ok_statuses=(200,206)`) and
  points it at a WDS endpoint gets exactly the failure `_probe_asserts.py:60-70` records as
  having "already happened once": every recorded failure launders itself into `pytest.skip`.
  The no-default `method=` does NOT stop this — the copied block already supplies a method.
- **Related probe (M20):** restore `method: str = "GET"` as a default in
  `_probe_asserts.py:54`. **SURVIVED — `38 passed`.** The removal of the default
  in `896d5c0` is itself unpinned. (The author assigns enforcement to the wrappers, and those
  ARE pinned for t3/t4/t5 — hence CARRY rather than REOPEN.)
- **Suggested closure:** derive the enumeration — glob `tests/test_probe_p*.py`, and for every
  module exposing `_source_reachable`, assert its observed (method, url, headers, ok_statuses)
  against a per-probe declared table. A new probe then either registers or reddens.

### C3 [MED] `len(t3.UNRESOLVED) == 7` is a COUNT proxy — the same shape `896d5c0` fixed three lines above

- **Probe (M21):** `test_probe_p3.py:67`, swap one member keeping the length:
  `"NONE"` -> `"ZZZ"`. **SURVIVED — `38 passed`.**
- `896d5c0` replaced the `len(NETWORK_EXCEPTIONS) == 18` count with full-set equality, but the
  `len(t3.UNRESOLVED) == 7` count three lines below in the same test was left as-is.
- **Blast radius:** dropping a real unresolved marker from p3's set is a false-green — a note
  emitting `DECISION-COUPLE-SHARE-SOURCE: NONE` would be accepted as a resolved answer.
- The sibling assertion `"NOT-FOUND" not in t3.UNRESOLVED` IS by-name, so the gate is not
  fully vacuous. **Closure:** full-set equality, same as the fix already applied beside it.

### C4 [MED] The invariant that justifies the accepted `_ACTIVE` residual is unpinned

- `_wds.py:14-18` accepts the `_ACTIVE`-not-reset residual on the stated ground that a stray
  fact "can never reach another run's note, because `provenance_header` reads only the log it
  is handed — never a free variable." `provenance_header`'s own docstring repeats it.
- **Probe (M19):** `_wds.py:149`, insert `log = _ACTIVE.get() or log` at the top of
  `provenance_header`. **SURVIVED — `38 passed`.**
- Behaviour-neutral today (I verified `_ACTIVE` equals the handed log at every current header
  call), and the combined M19+M15-p5 mutation IS killed — so the hazard-level gate holds. But
  the property the residual's safety rests on has no test of its own.
- **Closure:** one assertion — build log A, `new_run()` into log B, call
  `provenance_header(A, ...)`, assert the output reflects A.

### C5 [MED] `Fact` does not validate `kind`; a typo publishes a header whose arithmetic does not close

- **Probe** (executed against `_wds` directly):

```python
log = _wds.new_run()
_wds.Fact("1","derived","a"); _wds.Fact("2","cited","b"); _wds.Fact("3","derivd","typo")
# header summary line ->  'registered 3: 1 DERIVED and 1 CITED'      # 3 != 1 + 1
# and the cited list contains only '- 2 — b'
```

- `Fact.__str__` returns the CITED rendering for any kind that is not exactly `"derived"`, so
  the note body prints `3 [cited: typo]` while the header's "Externally cited figures:" block
  omits it and the count decomposition is false. Every probe's `_summary` is worded as a
  decomposition ("registered N: D DERIVED and C CITED"), so this is a false claim in a
  generated artifact — house rule #1.
- **Not reachable today:** all three probes use the `Fact.derived` / `Fact.cited` classmethods,
  and no probe constructs a `Fact` at module scope (AST-verified across p3/p4/p5). But
  `test_probes_common.py:90` itself uses the 3-arg form, which advertises it to the next author.
- **Closure:** `__post_init__` raises on `kind not in {"derived", "cited"}` — one line, and it
  is the same fail-loud posture the no-active-run branch already takes.

### C6 [LOW] p3's rewired `main()` is executed by nothing — now proven, not just disclosed

- **Probe (M15-p3):** drop the `new_run()` call site in `run_p3.py:419`. **SURVIVED — `38 passed`.**
- **Probe (M18):** inject a `NameError` into p3's note-building path (`run_p3.py:696`,
  `_table_number` -> `_undefined_helper`). **SURVIVED — `38 passed`.**
- `test_probe_p3.py` is a pure note-reader; `test_probes_common.py` execs the module body but
  never calls `main()`. A totally broken p3 `main()` ships green.
- Mitigated for *this* diff by PROBE 2 (live replay proves p3's `main()` is byte-correct today).
  Forward risk only. Closure requires p3 to grow injectable seams like p4's `_catalogue` /
  `_meta_batch`.

### C7 [LOW] The fail-vs-skip rule is dead code in CI; the unit assertion is its only guard

- **Probe (M22, M23):** neuter `if recorded not in NETWORK_EXCEPTIONS:` in `test_probe_p3.py`
  and `test_probe_p5.py`. **BOTH SURVIVED — `38 passed`.**
- Cause: `grep -c "LIVE PROBE FAILED"` over the three committed notes -> `0 / 0 / 0`, so
  `_fail_or_skip_on_recorded_failure` returns at its first line every run.
- Pre-existing structure, not diff-introduced, and `test_shared_network_exceptions_did_not_widen`'s
  full-set equality is the right compensating control — but it is the ONLY one. Worth knowing
  that relaxing that single assertion leaves the whole fail-vs-skip rule unguarded.

### C8 [LOW] `__pycache__` staleness can silently green a same-second, same-size probe edit

- `spec_from_file_location` validates `demoflow/probes/__pycache__/*.pyc` on
  (source mtime in whole SECONDS, source size). A same-second same-size edit reuses stale
  bytecode. This bit my own first mutation pass: after `git checkout --` restored `run_p3.py`,
  the suite still ran the mutated `_SCOPE` and reported 7 failures on a *clean* tree.

```
pyc-recorded mtime 1785277255 size 40224
source     mtime 1785277255 size 40224
STALE-BUT-CONSIDERED-VALID: True
```

- Reachable by any author editing probe prose (a same-length wording change is the normal case
  for `_SCOPE` / `_CITED_LABEL`) and re-running within the same second. The whole battery was
  re-run with `PYTHONDONTWRITEBYTECODE=1`; kill counts changed (e.g. M10 8->1), no verdict did.
- **Closure:** `PYTHONDONTWRITEBYTECODE=1` on the demoflow leg of `scripts/test-all.sh`, or
  `sys.dont_write_bytecode = True` in the three `_load_*` helpers.

## Edge cases that PASSED (sanity check — these were probed, and they are fine)

- Golden fixture is NOT a tautology: 12/12 cells regenerate from `e043500` code, and the fix
  commit did not touch the fixture even while changing `written_by=`.
- The 4 pinned mixes give full branch coverage of `provenance_header`.
- Double `main()` on the SAME module object: byte-identical output. The `_FACTS.clear()`
  motivation is genuinely handled by `new_run()`.
- The `_ACTIVE` residual behaves exactly as documented: a stray `Fact` after `main()` returns is
  silently accepted into the stale log, and does NOT leak into a later run (run3 == run1).
- No module-scope `Fact` construction in any probe (AST-verified) — the residual has no live
  trigger today.
- The fresh `contextvars.Context()` wrapper in `test_fact_outside_a_run_raises` is load-bearing,
  not decoration (M27 KILLED).
- No test-order dependency from the never-undone `sys.path.insert(0, probes_dir)`: each test
  file passes alone (18 / 3 / 4), and reversed collection order passes.
- Nothing in `probes/` shadows a stdlib module name (`run_p1..p5.py`, `_wds.py` only).
- `test_probe_p2.py` keeps its own `NETWORK_EXCEPTIONS` copy — the deliberate non-sharing holds.
- p4's removed `_table_number` / `_table_url` were already dead pre-extraction (git-verified at
  `e043500`), so their removal cannot change p4's output.
- `WDS_TIMEOUT=120` is identical on the wire to the old `TIMEOUT=120`; p5 keeps its own
  `TIMEOUT=120` for the CKAN/CSV hosts, unmerged.

## Coverage gaps / not tested

- p3 has no injectable seams, so its `main()` was exercised only through the live record/replay
  (once), not under fault injection (empty catalogue, vacuous metadata, partial `getData`).
- Concurrency: the `ContextVar` choice is justified by "two probe bodies interleaved on
  threads/tasks", and nothing here runs two probes concurrently. Untested in either direction.
- `run_p1.py` / `run_p2.py` and their tests are out of scope by construction and were only
  checked for the one cross-claim (p2's separate exception set).
- The committed `P3/P4/P5.md` notes were not diffed against a fresh live run — live data has
  moved since they were written, and separating vintage drift from a defect is out of scope for
  an extraction review.
