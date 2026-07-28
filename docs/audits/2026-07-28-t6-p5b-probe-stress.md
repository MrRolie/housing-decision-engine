# T6 — P5b probe adversarial stress pass (live-boundary)

Scope: `git diff 022434a..edf559a` — `demoflow/probes/run_p5b.py`,
`demoflow/probes/P5b-temp-resident-stock.md`, `demoflow/tests/test_probe_p5b.py`, plus
immediate callers (`demoflow/probes/_wds.py`, `demoflow/tests/_probe_asserts.py`,
`demoflow/tests/test_probe_contracts.py`).

Baseline: `./scripts/test-all.sh` -> hde 191 passed, demoflow 60 passed.
All probes run with `PYTHONDONTWRITEBYTECODE=1` and `demoflow/**/__pycache__` purged.
Every mutation verified APPLIED (`assert target in source` + `git diff --quiet` check) before
the run, and restored + verified with `git status` after. No mutation left the tree dirty.

**Live-boundary pass: DONE.** Full live regen (StatCan `getCodeSets` + `getAllCubesListLite` +
`getCubeMetadata`, CKAN `package_search`, the ISQ workbook) written to scratchpad:

```
committed  sha256: f1615114a26df97a8c2254fbf84bc0894e0084577dab5673f8be0532048b0df3
live-regen sha256: f1615114a26df97a8c2254fbf84bc0894e0084577dab5673f8be0532048b0df3
BYTE-IDENTICAL: True
```

Every recorded VALUE in the note reproduces from the live boundaries today. **No finding
under limb (a).** Both findings below are limb (b) / unpinned-gate.

---

# REOPEN

## REOPEN-1 [limb (b)]: the abbreviation check's conclusion is INVERTED relative to the number it cites, and its "MEASURED not assumed" claim is false

**Code:** `demoflow/probes/run_p5b.py:434-436` (computation), `:451-459` (the sentence).
**Note:** `demoflow/probes/P5b-temp-resident-stock.md` §1, "Abbreviation check" bullet.

```python
abbrev_hits = [... cubes whose title contains "npr" ...]
abbrev_pop  = [h for h in abbrev_hits if _lower_terms(h[1], POPULATION_TERMS)]
```

`abbrev_pop` is the npr-titled cubes that **also** match a POPULATION phrase — i.e. the ones
the phrase predicate **already caught**. Both branches draw the opposite conclusion:

- `not abbrev_pop` -> "so it surfaces **no** population cube the phrase predicate misses"
- `abbrev_pop`     -> "so it **DOES** surface population cubes the phrase predicate would miss"

An empty `abbrev_pop` means every npr-hit is *un*matched by the phrase predicate — evidence
*for* possible misses, not against.

### Probe (offline, two catalogue fixtures) — `scratchpad/p5b/probe_abbrev.py`

**Fixture 1** — catalogue carries a temporary-resident population cube titled with the bare
abbreviation only (`17109999 "Estimates of NPR stock by province, quarterly"`), which the
phrase predicate misses. Real output:

```
NOTE SAYS: ... a bare `"npr"` substring predicate matches **1** catalogue titles, of which
**0** also match a population term — so it surfaces no population cube the phrase predicate
misses.
SWEPT TABLE (what the phrase predicate caught):
    | `17100121` | Estimates of the number of non-permanent residents by type, quarterly | ...
```

`17109999` is absent from the swept table. The note states the abbreviation predicate
surfaced no missed population cube while it surfaced exactly one.

**Fixture 2** — a cube matching BOTH predicates (`17108888 "Estimates of non-permanent
residents (NPR), monthly"`). Real output:

```
NOTE SAYS: ... matches **1** catalogue titles, of which **1** also match a population term
— so it DOES surface population cubes the phrase predicate would miss; those are folded
into the swept list above.
SWEPT TABLE:
    | `17108888` | Estimates of non-permanent residents (NPR), monthly | non-permanent resident | POPULATION |
```

The phrase predicate caught it — it is in the swept table as POPULATION — while the note says
the phrase predicate would miss it. The trailing clause ("folded into the swept list above")
is TRUE, which is what makes the false clause beside it read as plausible.

### Why limb (b) as committed

Today's four npr-hits are "nonprofit institutions" cubes, so the *conclusion* is true by
accident. What is false **as committed** is the provenance claim:

> "Abbreviation check (why the predicate uses phrases, **MEASURED not assumed**)"

The conclusion is not measured. The cited `0` is logically irrelevant to it, and nothing in
the run computes the quantity the conclusion is about.

The self-referential tell is the very next clause: the author already fixed the "nonprofit"
gloss here by emitting the titles verbatim, explicitly because "that gloss was true only by
accident of today's catalogue". The **conclusion** one clause earlier is the same defect,
with the same accident, and survived the fix.

### Remediation

Measure the quantity the sentence is about — the npr-hits the phrase predicate does NOT catch
— and scope the conclusion to the verbatim list already emitted:

```python
abbrev_missed = [h for h in abbrev_hits if not _lower_terms(h[1], POPULATION_TERMS)]
```

Then say "N npr-matching titles are NOT caught by the phrase predicate; each is emitted
verbatim below" rather than concluding no population cube was missed. `abbrev_missed` is today
all 4 — the emitted list is already the honest evidence; only the sentence overreaches.

---

## REOPEN-2 [surviving mutant on a gate claimed load-bearing]: BOTH discriminators of the pick rule are unpinned; dropping the eligibility filter publishes an agriculture cube as the temporary-resident STOCK source, 60/60 green

**Code:** `demoflow/probes/run_p5b.py:517-522` (the `eligible_current` comprehension),
`:319-320` (`_is_current`).

The claim being violated — `run_p5b.py:514-516`:

> "The eligibility filter runs FIRST so the freshness ranking cannot be hijacked by a cube
> that is not a temporary-resident population source at all."

and `run_p5b.py:12-15`:

> "...and be **CURRENTLY MAINTAINED** ... All four are computed below from live responses AND
> all four GATE the verdict: geography, cadence and currency are enforced by the pick rule and
> the floor guard..."

### Mutations (both restored + verified)

| # | mutation | result |
|---|---|---|
| M7 | `[pid for pid in cand if cand[pid]["eligible"] and cand[pid]["current"]` -> drop `eligible` | **SURVIVED** 60 passed |
| M11 | `_is_current` -> `return True` | **SURVIVED** 60 passed |

Neither discriminator is pinned by any test.

### Consequence probe — `scratchpad/p5b/consequence.py`

Catalogue: one POPULATION cube ending `2026-04-01` and one PERIPHERAL cube ("Temporary
foreign workers in the agriculture sector, by category of farm revenue") ending `2027-01-01`.
Real output:

```
UNMUTATED  DECISION-SOURCE-PID  : 17100121
           DECISION-SOURCE-TITLE: Estimates of the number of non-permanent residents by type, quarterly
MUTATED    DECISION-SOURCE-PID  : 32100220
           DECISION-SOURCE-TITLE: Temporary foreign workers in the agriculture sector, by category of farm revenue
           DECISION-MEASURE-TYPE: STOCK
           DECISION-VERDICT     : LOCATED
```

With the eligibility filter dropped, the note publishes an agriculture-sector temporary-
foreign-worker cube as the temporary-resident STOCK source under a plain `LOCATED`, with the
whole suite green. This is precisely the hijack the comment says cannot happen.

**Live blast radius today: none.** The live pick (`17100121`, ends `2026-04-01`) has the
latest end date among all 10 swept cubes, so neither mutation changes today's committed note
— which is exactly why both survive. The defect is that the gate protecting the pick's
IDENTITY is load-bearing by claim and untested in fact.

### Remediation

Add an offline fixture to `test_probe_p5b.py` mirroring the consequence probe: a peripheral
cube with a later `cubeEndDate` than the population cube, asserting `DECISION-SOURCE-PID` is
the population cube. A second fixture with an ARCHIVED cube carrying the latest end date pins
`_is_current`.

---

# CARRY

## C1 — the test's guard taxonomy is wrong about itself: `_guard_codesets` is attribution-only, not safety-load-bearing

`demoflow/tests/test_probe_p5b.py:349-351` asserts:

> "`_guard_codesets` is ALSO safety-load-bearing on the cadence axis: neutered, an empty code
> set yields `DECISION-CADENCE: (frequencyCode 9 …)` with an EMPTY label."

Probe — `scratchpad/p5b/probe_guards.py`, real output:

```
case                                     VERDICT                FAILED-AT
A-baseline      _guard_codesets ARMED    UNKNOWN-PROBE-FAILED   wds-codesets
A-NEUTERED      _guard_codesets          UNKNOWN-PROBE-FAILED   wds-meta
A-NEUTERED-BOTH codesets+pick            LOCATED                None      <- cadence label EMPTY
EMPTYCAT-NEUT   _guard_sweep             UNKNOWN-PROBE-FAILED   wds-meta
NOMATCH-NEUT    _guard_sweep             UNKNOWN-PROBE-FAILED   wds-meta
EMPTYDIM-NEUT   _guard_pick              LOCATED                None      <- GEO "0 members"
```

Neutering `_guard_codesets` alone changes only the boundary ATTRIBUTION
(`wds-codesets` -> `wds-meta`); the verdict stays `UNKNOWN-PROBE-FAILED`. It is structurally
impossible for it to be safety-load-bearing: when `freq_map` is empty, `_guard_pick`'s
`code not in freq_map` (`run_p5b.py:388`) is *always* True. The fabricated LOCATED the
docstring describes requires **both** guards neutered (row 3).

So the true taxonomy is: **`_guard_pick` is the sole safety-load-bearing guard;
`_guard_codesets` and `_guard_sweep` are both attribution-only.** The author's stated-risk list
inherits the same error ("`_guard_sweep` is self-declared MESSAGE-QUALITY only" implies the
other two are not). A P6 author copying this docstring inherits a wrong safety model.

Not a REOPEN: the claim is in the gate file, not in the generated note, and no recorded value
is wrong.

## C2 — the previously-REOPENed "containing geography" gloss is now DECLARED but unpinned; a one-token edit republishes a false geography claim, green

`run_p5b.py:114` `MODELED_CMA_PROVINCE = {"Montréal": "Quebec", "Québec": "Quebec"}`.

M10: change both values to `"Ontario"` -> **SURVIVED**, 60 passed. Published output
(`scratchpad/p5b/consequence.py`):

```
MUTATED DECISION-PICK-LIMIT: ... their DECLARED containing province(s) ['Ontario'] — declared
beside MODELED_CMAS, not inferred here — ARE present as member(s) ['Ontario'], so that is the
finest geography this source offers for them; ...
```

On the LIVE member list (14 members incl. Ontario) this publishes a flatly false geography
claim with the suite green. The declaration is honest about being DECLARED, and it is correct
today — but the fix for the prior REOPEN moved the claim from prose into a constant without
pinning the constant.

Sub-point: the trailing clause "**so that is the finest geography this source offers for
them**" is neither declared nor computed. Nothing verifies that no finer member containing
them exists; the declaration only asserts containment.

## C3 — §2's blanket "the only measure-type claim this note makes about a swept cube" is falsifiable by the note's own `_reject` branch — the exact sibling of the previously-fixed blanket claim

`run_p5b.py:550-551` emits, for a non-pick candidate:
`"only FLOW markers matched ({...}); no stock marker"`.

Probe — a rival cube titled "Components of growth of non-permanent residents, net migration,
annual". Real output, both lines in the SAME generated note:

```
- `17100999` — series ends 2025-01-01, earlier than the pick's 2026-04-01; only FLOW markers
  matched (['components of', 'growth', 'net migration']); no stock marker.
...
The pick's measure type is decided in §3 ... and is the only measure-type claim this note
makes about a swept cube.
```

The branch does not fire today (no swept candidate has flow markers without stock markers), so
the sentence is TRUE as committed — hence CARRY, not REOPEN. But this is the same shape the
prior pass REOPENed ("a blanket 'the only claim this note makes' that the note's own later
section falsified"), surviving in a section the fix did not touch. The fix should be
structural: make the sentence a function of whether the branch fired.

## C4 — §4's `class_scoped` proxy is demonstrably wrong on the live population; today it fails SAFE

`run_p5b.py:814`, `:821-822`. `combined` requires `not class_scoped`, a PACKAGE-TITLE test used
as a proxy for "publishes the temporary-resident total".

Live CKAN enumeration (`scratchpad/p5b/ckan_dump.py`; counts reproduce the note exactly:
52 results, 11 IRCC packages, 6 class-scoped). The package that fails on exactly ONE condition
— *Specialized Research Datasets: Temporary Resident* (`n_cma_live=6`, `n_stock=0`,
class_scoped `[]` -> "total (no class term)") — has **all 54 of its resources
permit-class-split**:

```
Canada - Temporary Resident - International Mobility Program - Census Metropolitan Area - 2000 - 2016
Canada - Temporary Resident - Study Permit - Census Metropolitan Area - 2000 - 2016
Canada - Temporary Resident - Temporary Foreign Worker Program - Census Metropolitan Area - 2000 - 2016
```

There is no total-scope resource in it. Had IRCC named those CMA resources with a
point-in-time token, `combined` would have been 1 and the note would have printed
"inspect these before treating the StatCan pick as the only maintained option" about a package
that cannot supply the total.

**Direction check (keeps the finding honest):** `combined` is a WEAKER condition than the
property, so `combined == 0` does imply "none offers" — the committed conclusion **is sound**.
Verified by exhaustive enumeration: exactly one resource across all 11 packages is both
CMA-named and point-in-time-named in a single resource —

```
Canada – International Mobility Program Work Permit Holders under Post-Graduate Employment
on December 31st by Province/Territory and Census Metropolitan Area (CMA) of Intended Destination
```

— and it sits in the work-permit-class package, i.e. a subset, not the total. Alternative
point-in-time phrasings ("with valid permit(s) in calendar year", "on Dec. 31") and alternative
geography phrasings were swept; none produces a CMA-level point-in-time total.

Sub-point: `stock_res` (`:801-804`) is computed over ALL resources while `cma_live`
(`:799-800`) excludes `[ARCHIVED]` ones. Asymmetric, but the column headers disclose it
("point-in-time-named" vs "CMA-named & not [ARCHIVED]") and it only makes `combined` larger —
safe direction.

## C5 — the STOCK/FLOW marker scopes are asymmetric and glossed symmetrically

`run_p5b.py:621` computes `title_stock` over the **title only**; `:506` computes `flow_hits`
over `_searchable_text` (**title + every dimension name + every member name**). They are
combined in one formula at `:622-623` and glossed symmetrically in §3 ("Title stock markers
[...]. No flow markers.") and in `DECISION-MEASURE-TYPE`.

Live headroom probe (`scratchpad/p5b/livepop.py`): the pick's non-geography dimension members
are `['Total, non-permanent residents', 'Total, asylum claimants...', 'Work permit holders
only', ...]` — no flow marker today, full-text flow markers `[]`.

Consequence if StatCan adds an NPR-type member named e.g. "Net change" or "Balance": a member
name flips `flow_hits`, the measure computes AMBIGUOUS, and the note re-runs to
`LOCATED-NOT-STOCK` with the suite still green. **Direction is SAFE** (it downgrades the
verdict, it cannot fabricate a STOCK). Highest-value trap for the P6 copy-paste author.

## C6 — §5's "measured reason" is half tautological, and "over the year" is untied

`run_p5b.py:889` selects the column with `"solde" in stack(c).lower()`. The note then gives
"the label CONTAINS 'Solde'" as the **measured reason** the column is not a stock — a property
guaranteed by the search predicate that found it. The negative-value half (`-72314`) is a real
measurement; the label half cannot discriminate.

Verified the search is unambiguous today: exactly one column matches
(`columns matching the ISQ predicate: [18]`), out of 7 "Solde"-prefixed columns — so `found[0]`
is not silently choosing among candidates.

"a net FLOW **over the year**" is hand-typed; nothing reads the period. It is TRUE — the
workbook's own header states it (`row 8 col 3 = 'de (t) à (t+1)'`, `row 7 col 3 = 'du 1er
juillet'`) — but the probe never reads that cell, so the adjective is untied to computed state.
It is two rows above the ones already being read.

Scope sub-point: because the search requires "solde", a STOCK NPR column in the same workbook
would never be found, and §5 would still record the workbook as not filling the slot.

## C7 — unpinned guards and branches (mutation survivors, lower consequence)

All restored + verified.

| # | mutation | result | note |
|---|---|---|---|
| M6 | delete the `[FILL` scan call site (`:1088-1090`) | **SURVIVED** | `test_p5b_no_unfilled_placeholder` reads the committed note, not a run — the runtime raise is unpinned |
| M8 | `cma_available = all(...)` -> `any(...)` (`:600`) | **SURVIVED** | equivalent on today's data (both CMAs 0); differs on a cube carrying exactly one modeled CMA |
| M9 | drop `eligible` filter from `cma_bearers` (`:683-685`) | **SURVIVED** | see C8 |
| M13 | delete `_reject`'s one-time-period branch (`:545-547`) | **SURVIVED** | the §2 rejection reasons for `33100678` and `98100361` lose their one-time-period clause; §3b's disqualifier is computed separately at `:698-701` and survives |

Killed, for contrast (these ARE pinned): M1 (revert the label-less frequency filter — the
just-closed CRITICAL, **KILLED**), M2/M3/M4 (delete each guard's CALL SITE — all **KILLED**),
M5 (STOCK discriminator removed from the verdict — **KILLED**), M12 (measure gloss
un-conditioned — **KILLED**).

## C8 — §3b's scope claim is wider than its computation

`cma_bearers` (`:683-685`) filters to `eligible` (POPULATION-term) candidates, but the
else-branch (`:717-718`) says "NO candidate among the **{len(swept)}** swept carries both
modeled CMAs", and `DECISION-PICK-LIMIT` says "the only **swept** cube carrying both". A
peripheral candidate carrying both CMAs would be invisible to the computation while the prose
claims coverage of all swept cubes.

Not currently false: verified live that all five peripheral candidates show
`Montréal:0, Québec:0`, and the else-branch is not reached at all (`cma_bearers` is non-empty).

## C9 — cross-artifact claim: "the demand model's NPR input" is asserted twice about a system that does not exist in the repo

The note asserts, in two places:

- §5: "this column is recorded as a complement (**it is already the demand model's NPR input**)"
- DECISION standing rule: "NOT the demand model — **the demand model's NPR input is** the ISQ
  compo net-flow column measured in §5"

`run_p5b.py` never opens the demand model, the spec, or anything but the workbook cell. Primary
source check:

```
$ find demoflow/src -name "*.py"
demoflow/src/demoflow/__init__.py
demoflow/src/demoflow/errors.py
$ grep -rn -i "npr|non_permanent|non-permanent|solde" demoflow/src/ src/
(no matches)
```

There is no demand model. The `demand/` package is a planned layout at spec line 88, not built.
So "it is **already** the demand model's NPR input" is false in the present tense about the
built system.

**Why CARRY and not REOPEN — stated so the controller can overrule.** The substantive content
is TRUE at the design level: spec §6 line 247 states "arrival cohorts come from the `compo-*`
annual flows", and spec line 120 exempts "net migration components" as signed flows. So the
compo net-flow columns ARE the designated demand-side arrival input, and the note's purpose here
— preventing a substitution between the tripwire stock and the demand flow — is correct and
worth keeping. Only the tense overstates. Limb (b) is therefore not cleanly met.

What IS defective: this is a hand-written, inferred cross-system claim in an artifact whose
house rule #1 forbids exactly that, and it is the same class as the four glosses the prior pass
REOPENed (notably "maintained", which was also arguably true and was still folded). It is the
one claim class where "the value is correct" gives zero signal, because there is no computed
value beside it at all. Cheapest fix: tense it to the design and cite it —
"per spec §6 the demand model's NPR input is designated as the compo net-flow column".

## C10 — three more hand-typed conditions beside computed values (the REOPEN-1 family)

- **§3b: "They are separate products with separate reference periods *and methods*."** The
  reference periods ARE computed (`2021-07-01..2026-04-01` vs `2021-01-01..2021-01-01`).
  "and methods" is hand-typed — nothing inspects methodology, and the footnote quoted beside it
  covers DEP-vs-IRCC, not DEP-vs-Census. Exactly the shape of the fixed "maintained" gloss (a
  condition asserted that was not among those tested), surviving in a section the fix DID touch.
- **§1: "so every absence claim below is scoped to a WIDER population than the pick pool."**
  Analytically, `swept ⊇ pool` only. It is strictly wider today because PERIPHERAL_TERMS matched
  5 cubes; if they matched none, `swept == pool` and "WIDER" is false with the suite green.
- **`_summary`'s universal quantifier** (`run_p5b.py:159-168`): "Untagged numerals ... **each**
  traceable to the live response or the named file this run read." `ISQ_PLAN_COL = 18` (`:94`)
  and `ISQ_HEADER_ROWS = range(5, 10)` (`:92`) are constants typed from the plan, traceable to
  neither, and both print into §5 ("matches the plan's pinned column 18", "header rows
  [5, 6, 7, 8, 9]"). The sentence is universally quantified and the note contains counterexamples.

## C11 — `DECISION-GEO-LEVEL`'s "other" arithmetic can publish a negative count

`run_p5b.py:995`: `e['n_geo'] - n_canada - e['n_cma_marked'] - e['n_ca_marked']` double-subtracts
any member carrying both a CMA marker and a `(CA)` marker. Probe with members
`['Canada', 'Sherbrooke (CMA) and (CA), Que.', 'Trois-Rivières (CMA) and (CA), Que.']`:

```
DECISION-GEO-LEVEL: 3 members: 1 named exactly "Canada", 2 carrying a CMA marker,
2 carrying a (CA) marker, -2 other; the full member list is emitted verbatim in §3
```

The gate at `test_probe_p5b.py:191` only regexes the leading `[1-9]\d* members`, so a negative
"other" passes. **Not live-reachable today** — verified across the pick, `98100361` (174
members, 43 CMA / 117 CA) and `17100158`: `BOTH-marked: 0` on all three. Defensive only.

---

# Edge cases that PASSED (probed, and fine)

- **Live regen is byte-identical** to the committed note across all five boundaries. Every
  recorded value reproduces. `sha256 f1615114…` confirmed.
- **`_guard_pick` is genuinely safety-load-bearing.** Neutered -> `LOCATED` with
  `DECISION-GEO-LEVEL: 0 members`. Its call-site deletion (M2) is KILLED.
- **All three guard CALL SITES are pinned** (M2/M3/M4 all KILLED) — the guards are wired, not
  just body-tested.
- **The just-closed empty-cadence CRITICAL is pinned.** M1 (revert the label-less filter) is
  KILLED by `test_p5b_floor_guard_earns_verdict`; scenario (b) is doing real work.
- **The STOCK discriminator gates the verdict** (M5 KILLED) and the level-vs-movement gloss is
  conditioned on the MEASURE, not the footnote (M12 KILLED).
- **The NOT-MEASURED branches are honest.** Ran the probe with `openpyxl` absent: §5 recorded
  `ISQ COMPARISON NOT MEASURED THIS RUN: ModuleNotFoundError`, and the `DECISION-PICK` scope
  string correctly narrowed to "(NOT MEASURED this run, so NOT part of the comparison: ISQ
  compo (§5))" while the standing-rule sentence switched to "(NOT measured this run — see §5)".
  The verdict was unaffected. Exactly as designed.
- **§4's headline conclusion is sound** — exhaustively enumerated (see C4).
- **§4/§1 counts reproduce live**: CKAN 52 results / 11 IRCC packages / 6 class-scoped;
  catalogue 8214 / 10 swept / 5 population.
- **The contract glob discovers p5b**: 3 parametrized contract tests collected
  (`test_probe_main_routes_its_header_through_provenance_header[p5b]`,
  `test_probe_declares_its_provenance_prose[p5b]`,
  `test_reachability_wrapper_matches_its_own_probes_method[p5b]`).
- **The reachability wrapper is POST**, matching `getCubeMetadata`, and the contract gate
  enforces it — no GET-launders-into-skip vector.
- **The ISQ column search is unambiguous** — exactly one of 38 columns matches, out of 7
  "Solde" columns.
- **Provenance arithmetic closes**: 11 = 8 DERIVED + 3 CITED, matching the `Fact.derived` /
  `Fact.cited` call counts.
- **Every `spec:473` assertion in the note checks out against the primary source.** ~10
  assertions rest on it and the spec was never opened by the probe, so this was checked
  directly — `docs/specs/2026-07-21-demoflow-demographic-scenario-module-design.md`:
  - line 471: "(indicator, current value, source, as_of, threshold band)" — supports the note's
    "current value + as_of + freshness limit";
  - lines 473 + 475-476: `temporary-resident stock` is declared `wired`, "source named at probe
    §11"; UNKNOWN fires on source-unavailable; "a stale baseline is NEVER reported as
    within-band" — supports the note's `DECISION-TRIPWIRE-STATUS` wording near-verbatim;
  - lines 571-573 (§11 item 5b): "Temporary-resident **STOCK** source (codex F5): StatCan NPR
    estimates (**17-10-0121-01 family**) vs IRCC temporary-resident tables — **pick one, record
    schema + cadence**; until wired the tripwire reports UNKNOWN, never a stale within-band."
    The pick, the two candidate families, the deliverable and the fallback all match. The
    "spec:473 consumes a STOCK" framing — on which the whole `LOCATED` / `LOCATED-NOT-STOCK`
    vocabulary rests — is correct.
- **Determinism at fixed input**: `swept.sort()`, `pkgs` sorted by title, `found[0]` — repeated
  runs at fixed input are stable.

# Not tested

- The CONTENT of the CKAN/StatCan resources (only names and metadata). Whether IRCC's CMA
  tables are stocks or flows cannot be settled from resource names; C4 is scoped accordingly.
- Concurrency of the `_ACTIVE` ContextVar across interleaved probe runs (documented residual in
  `_wds.py:11-16`; unchanged by this diff).
- StatCan WDS behaviour under partial/HTTP-error responses per-pid (`_meta` drops unresolved
  pids silently; the `resolved=False` path is emitted as a rejection reason but was not driven
  against a live error response).

---

# Fold disposition (implementer, 2026-07-28)

Folded in `fix(demoflow): P5b — correct the inverted abbreviation-check inference, pin the
pick-rule discriminators, and correct two self-descriptions (adversarial fold)`.

| finding | disposition |
|---|---|
| REOPEN-1 | **FOLDED.** Computation replaced: `abbrev_missed = abbrev_hits - swept_pids` (the set that bears on the conclusion) instead of the population-intersect. Both branches reworded to state what that number means; the "MEASURED not assumed" parenthetical is gone. Every npr-matching title is emitted in a table with a swept YES/NO column so the count is checkable. Pinned by `test_p5b_abbreviation_check_measures_what_it_concludes` using both audit fixtures (`17109999` -> 1 missed, `17108888` -> 0). Reverting the computation is RED. |
| REOPEN-2 | **FOLDED.** `test_p5b_pick_rule_discriminators_are_load_bearing` builds a catalogue where the NON-eligible cube (`32100220`, ends 2027-01-01) and the ARCHIVED eligible cube (`17100023`, ends 2028-01-01) are both FRESHER than the population cube, and asserts the pick is still `17100121`. Dropping `eligible` -> RED; `_is_current` -> True -> RED. |
| C1 | **FOLDED.** Verified the structural-impossibility argument independently before accepting it: neutering `_guard_codesets` leaves the verdict UNKNOWN in both the empty-code-set and the no-description case and moves only `FAILED-AT` (wds-codesets -> wds-meta). The docstring now grades it ATTRIBUTION-ONLY and states why it structurally cannot be otherwise. `_guard_pick` is named the only safety-load-bearing guard. |
| C2 | **FOLDED.** `_province_corroborated` checks the declared province against the province abbreviation in each CMA member's OWN live name (`"Montréal (CMA), Que."` -> `que`), independent evidence this file does not control. Result emitted in §3b whatever it is. `test_p5b_declared_province_must_be_corroborated` tests BOTH directions — the positive-only half let `_province_corroborated -> True` and call-site deletion survive, so the wrong-declaration case is what actually pins it. |
| C3 | **FOLDED.** Blanket dropped rather than re-narrowed (third instance of the shape in this file). Replaced with an explicit statement that no blanket is claimed, naming the two other places measure type is discussed. |
| C5 | **FOLDED.** The asymmetry is now stated in the note: stock markers are TITLE-only, flow markers span title + dimension names + member names, and the formula can downgrade a STOCK claim but never manufacture one. |
| C9 | **FOLDED.** Both sites reframed from present-tense fact to the SPECIFIED consumer (spec §6), explicitly noting no demand model is implemented in demoflow yet. |
| C4, C6, C7, C8, C10, C11 | **CARRIED** — not folded this pass, per coordinator instruction. Recorded here for the field report. |

Verification after the fold: hde 191 + demoflow 63; `test_probe_contracts.py` 14 passed
unmodified; live-regen byte-identical, committed note sha256
`02135b368292dc64cc027218e7fe66924b7f684c8e3b0e8980ee4007a4c79e84`; all six mutations on new
gate code RED (each verified APPLIED before the run).
