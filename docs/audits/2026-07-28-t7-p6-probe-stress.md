# T7 P6 probe — task-scoped adversarial review (STANDARD tier)

Worktree `housing-decision-engine.demoflow-t1`, branch `feat/demoflow-tranche1`.
Under review: `git diff 73d2ad9..HEAD -- demoflow/` (`84a3fbf`, `b46692e`, `c966b11`, `8940f2a`, `caaccb5`).

Status: COMPLETE. 2 REOPEN / 7 CARRY (see VERDICT SPLIT).

## Confirmed so far

### F1 [REOPEN limb (b)] — the note promises a "release line" it also says does not exist
`demoflow/probes/run_p6.py:1066-1068` appends UNCONDITIONALLY.
Emitted note `P6-mrc-isq-hunt.md:63` ends: "...the caption and release line below are read
from its own bytes and state which edition it is."
Emitted note `P6-mrc-isq-hunt.md:67` states: "No cell in the header block names a diffusion
date this run."  (`diffusion == ""`)
The artifact forward-references evidence it does not contain — structurally identical to the
already-fixed §2 forward-reference defect.
Rendered wording CHECKED (not assumed): line 63 ends as one conjoined promise — "the caption
and release line below are read from its own bytes and state which edition it is" — with no
hedge a reader could parse as "release line, if present".

### F2 [CARRY-high] — `test_probe_p6.py:371` is a DEAD gate (regex cannot match)
Gate 2's marker regex requires `NOT ANSWERABLE from this workbook (`; the generator
(`run_p6.py:1768`) emits `NOT ANSWERABLE from what this run read of this workbook (`.
Verified: match -> None on the committed note; the sibling at `test_probe_p6.py:865` (correct
rescoped literal) matches. The comment at `test_probe_p6.py:862-864` claims "Gate 2 enforces
this on the COMMITTED note" — a false coverage claim above a dead sibling.
Class (B): §3c's prose was rescoped; the test literal went stale.

### F3 [CARRY] — stale spec quote in a test assertion message
`test_probe_p6.py:183-184`: `spec §8 asserts "no MRC workbook exists"`. §8 was AMENDED in
`b46692e`; the note's own §4 reports that marker ABSENT. Class (B) survivor.

### F4 [CARRY] — `run_p6.py` docstring's "never reproduces its words" is falsified by its own emitter
Docstring lines 11-16: "WHY NO §8 SENTENCE IS QUOTED ANYWHERE IN THIS FILE ... Every other
reference in this file names the section and never reproduces its words."
But the §5 standing-rule block (emitted on ALL FOUR branches, e.g. `run_p6.py:1778-1782`)
reproduces spec §8 VERBATIM: "ranking members, never balance participants, never emitted in
`ScenarioPrior`". Confirmed present in the live spec at line 499 (modulo backticks).
Currently TRUE against the spec, so not limb (b) — but it is an unchecked cross-artifact
text dependency of exactly the class the docstring claims the file does not have.

### CLEARED — the two plan-body claims
`docs/plans/2026-07-21-demoflow-tranche1.md:762-763` carries exactly
`pop-as-mrc-base.xlsx` / `pop-mrc-base.xlsx`, and the sketch at :770 uses
`urllib.request.Request(url, method="HEAD")`. Both note claims hold.

### CLEARED — §4 positional assumption
`couronne-nord precision` matches 2 spec lines (499 = §8 Geography row, 574 = §11 item 6);
first is indeed §8. Note reports "matched 2 line(s)". Correct.

### F5 [REOPEN limb (b)] — §2's hreflang dedup explanation is refuted by the document
`P6-mrc-isq-hunt.md:27`: "**25543** distinct `<loc>` entries (deduped: the raw document repeats
each url once per hreflang alternate, so an un-deduped count would overstate the population
every absence claim below is scoped to)". Same claim in `run_p6.py:373-377` (`_locs` docstring).

Measured on a live fetch of `sitemap.xml` (13,501,035 bytes):
- `<url>` elements = 25705, `<loc>` occurrences = 25705 -> **exactly one `<loc>` per `<url>`**.
- hreflang alternates ARE present (50672 `hreflang` attrs) but as `<xhtml:link ... href=...>`
  attributes; the `<loc>` regex never sees them. **No url is repeated per hreflang alternate.**
- Distinct urls appearing >1x: 105 of 25543 (**0.41%**), accounting for the 162 removed
  occurrences — and they are duplicate `<url>` entries for cartovista map pages
  (`/cartovista/ivt_mrc/index.html` etc.), unrelated to hreflang.
- An un-deduped count would be 25705 vs 25543: an overstatement of **0.63%**, not the ~2x the
  stated mechanism implies.

The number 25543 is CORRECT; the sentence beside it states a mechanism the document refutes.
Depth-2 exactly: the number being right is what stopped the clause being checked.
(INFERENCE, not measured — flagged as such deliberately, since this finding is itself about an
unmeasured explanation beside a correct number: the fr/en `/fichier/` story is TRUE for the
33->22 slug dedup and reads like it was carried over to the `set()` dedup, where it does not
apply. Treat as a repair hint, not a finding.)

### F6 [REOPEN limb (b)] — §3's "a substring test ... counts zero labels below it" is false, and understates the failure mode
`P6-mrc-isq-hunt.md:68`: "...while a substring test locks onto the caption row (cell A1 above,
which also contains \"mrc\") and counts zero labels below it." Sibling in `run_p6.py:137-141`.

Measured by re-running `_find_header`/`_labels` against the live picked workbook
(`composantes-demographiques-projetees-mrc-du-quebec.xlsx`, 517264 bytes):
```
PREFIX    -> header row 2 col 1 | n labels = 122
SUBSTRING -> header row 0 col 0 | n labels = 109      <-- note claims ZERO
EQUALITY  -> header row 2 col 1                       (equality does NOT miss on THIS file)
```
The substring path does lock onto the caption at (0,0) — that half is true — but it then reads
column 0, the `Code` column, and yields **109** labels: `['1', '1.', '10', '11', '12', ...]`.

This matters beyond the wrong number. The note's stated consequence ("zero labels") is the
fail-SAFE one: zero labels trips `_guard_body`'s label branch -> `VacuousProbeError` -> UNKNOWN.
The ACTUAL consequence is fail-SILENT: 109 >= 1, so `_guard_body` passes, and the run publishes
a LOCATED whose `DECISION-MRC-LABEL-COUNT` is 109 numeric codes presented as geography labels.
No label-count or wrong-column gate catches it: `[1-9]\d* distinct geography labels` passes and
the decomposition 0+109=109 closes. The note misdescribes the rejected alternative as caught
when it is not — and asserts "the reason is visible in this run's own evidence" for a claim
that is not in its evidence.

RECONCILIATION with mutation M6 (KILLED), because the two would otherwise read as inconsistent:
M6 died via gate 6 (`test_probe_p6.py:706`, RA corroboration) and gate 7's residual-(i)
distinctness check (`:887`) — on the fixtures the substring path collapses `ra_col` to -1, so
"1 publish a SEPARATE..." becomes 0 and the couronne search goes NOT CHECKABLE. Measured
failure output:
```
E  AssertionError: Les Moulins was not corroborated ... '| RA14 Lanaudière | Les Moulins | **NO** | — | NOT CHECKABLE |'
E  AssertionError: residual (i) reported the same axis token for three different RA shapes ... assert 1 >= 3
```
So the wrong-column LOCATED is caught only INCIDENTALLY, by residual gates that happen to
collapse on the fixture shapes — never by a check on the geography column itself. On the LIVE
workbook `_guard_body` passes 109 labels and `DECISION-MRC-LABEL-COUNT` would read 109.

### F7 [CARRY] — §3c's RA-subtotal exclusion branch is unreachable on this data; its code comment is false
`run_p6.py:650-654` comments: "The RA's OWN subtotal line carries the same RA code as its MRCs.
Counting it as a member would inflate every set by one and make an EQUAL relation unreachable."
Measured: all 17 `NN  Name` subtotal DATA rows carry `RA1 = None`, so they are dropped one
branch earlier by `if row[geo_col] is None or row[ra_col] is None: continue`. The
`AGGREGATE_LABEL_PATTERN` exclusion never fires — which is why the note prints
`RA-subtotal rows excluded: 0` for all three RAs. The printed 0 is honest; the code comment
asserting they carry the RA code is not.

### CLEARED — the fr/en slug dedup (33 -> 22)
Measured: 11 slugs carry 2 locs each with `langs=['en','fr']`, 11 carry 1 -> 11*2+11 = 33 -> 22.
`P6-mrc-isq-hunt.md:29` is correct in both value and mechanism.

### CLEARED — HEAD/GET, independently re-measured this run
`GET  -> 200` (`application/vnd.openxmlformats-...sheet`, Content-Length 517264, prefix
`504b030414000600`); `HEAD -> 404`. Both guessed slugs `-> 404` on GET. All recorded.

### F8 [CARRY] — §3b asserts "Every one of the N verified candidates is opened" unconditionally
`run_p6.py:1229-1231` emits `f"Every one of the {len(verified)} verified candidates is opened..."`
using `len(verified)`, while the split beside it is scoped to `len(opened)`.
Executable probe (offline, 2 eligible candidates, the 2nd raising on open) produced a note
whose §3b reads:
```
Every one of the 2 verified candidates is opened and asked the same question ...
The split is **1 / 0 / 0**
| `...-mrc-du-quebec.xlsx`      | yes                                            | ...
| `population-projetee-...xlsx` | **NO — ValueError: File is not a zip file**    | ...
```
The sentence is contradicted by the table directly under it. Not false on the committed note
(15/15 opened), so CARRY — but reachable in production (download truncation, corrupt zip,
timeout on the 17MB candidate). Mutation M15 (silently drop unopenable candidates) SURVIVED:
`_wire` patches `_workbook_rows` to a lambda that cannot raise, so NO fixture reaches the
`opened: False` branch at all.

### F9 [CARRY] — `_ra_axis_usable` is a PROXY: an over-matching RA header is read as a per-MRC RA code column
Property: "this edition publishes a separate column carrying a per-MRC RA CODE".
Predicate (`run_p6.py:404-414`): `ra_col >= 0 and ra_col != geo_col`, where `ra_col` comes from
`RA_HEADER_PATTERN.match(t) or any(k in t for k in RA_HEADER_MARKS)` — an unanchored `in` test.
Constructed input where the property is VIOLATED but the predicate SATISFIED: a header cell
`"Population de la région administrative"` at col 2 (geo col 1), carrying population values.
Executable probe output:
```
§3b RA-axis cell : **SEPARATE column `Population de la région administrative`** (col 2)
RESIDUAL-I       : 1 publish a SEPARATE administrative-region column
RA-CORRESPONDENCE: 0 of 2 declared targets corroborated against the opened workbook's own
                   SEPARATE RA column (column 2, header 'Population de la région administrative')
RESIDUAL-II      : RA14 -> EMPTY; RA15 -> EMPTY; RA16 -> EMPTY
```
§3b's stated purpose is that fusing states "would report a machine-readable axis where none
exists". The three-state split closed the geography-header route to that outcome and left the
header-over-match route open. Mitigating (stated honestly): §3 does emit
"**2 target(s) DISAGREE ... treat every RA grouping in this note as UNSUPPORTED until
reconciled**", so the run is not silent. Not triggered on the committed note — the real `RA1`
column genuinely carries `['14']/['15']/['16']` beside the targets (verified live).

## Mutation battery (all verified-applied via `assert target in source`, count==1; restored + `cmp`-checked)

| # | mutation | verdict | fixture-reachable? |
|---|---|---|---|
| M1 | delete §3's "release line" clause (F1 subject) | **SURVIVED** | reachable — pure prose, no gate |
| M2 | §3c call site re-derives `ra_col >= 0` | KILLED | yes |
| M3 | `_ra_axis_usable` body weakened | KILLED | yes |
| M4 | §3 call site computes `ra_usable` weakly | KILLED | yes |
| M5 | evidence dict carries weak `ra_usable` (b0 seam) | KILLED | yes |
| M6 | `_find_header` PREFIX -> SUBSTRING (F6 subject) | KILLED | yes |
| M7 | `_find_header` PREFIX -> EQUALITY | KILLED | yes |
| M8 | delete §2's hreflang dedup clause (F5 subject) | **SURVIVED** | reachable — pure prose, no gate |
| M9 | `_relation_head` handles only the em-dash tail | **SURVIVED** | reachable, but gate 7 checks `"NOT COMPUTABLE" in ...` (substring), and gate 2's strict `allowed` vocabulary check runs ONLY on the committed note, which carries the em-dash form |
| M10 | co-occurrence drops `and not n_sep` | **SURVIVED** | **UNREACHABLE** — every fixture sitemap yields exactly ONE candidate, so `ra_separate` and `ra_absent` can never both be non-empty |
| M11 | `PREFERRED_LANG_PATH` `/fr/` -> `/en/` | **SURVIVED** | **UNREACHABLE** — no fixture sitemap contains an `/en/` loc (grep: 0) |
| M12 | `_guard_body` label branch weakened | KILLED | yes |
| M13 | `_is_workbook_response` drops magic screen | KILLED | yes (and `_guard_body`'s "BACKSTOP" branch is what fires — the author's honest grade holds) |
| M14 | `_declared_ra_number` always `""` | KILLED | yes |
| M15 | `_probe_editions` silently drops unopenable candidates | **SURVIVED** | **UNREACHABLE** — `_wire` patches `_workbook_rows` to a lambda that cannot raise |
| M16 | `_ra_membership` aggregate-row exclusion removed | **SURVIVED** | **UNREACHABLE twice** — no fixture carries an `NN ` label, and on live data the 17 subtotal rows carry `RA1 = None` so they are dropped a branch earlier (see F7) |
| M17 | §3b `ra_named_only`/`ra_absent` inverted | KILLED | yes |
| M18 | `_labels` drops distinctness (set -> list) | **SURVIVED** | **UNREACHABLE** — no fixture column carries a duplicate label; the live "122 **distinct**" figure depends on it |

Baseline: 74 passed. 18 mutations: 10 KILLED, 8 SURVIVED (5 of the 8 unreachable by any fixture).

### F10 [CARRY] — the swept-population scope excludes 26 locs that satisfy the note's own stated predicate
`P6-mrc-isq-hunt.md:290`: `DECISION-SWEPT-POPULATION: the 25543 ISQ sitemap locs swept in §2
(22 matched the MRC×population predicate, 15 eligible) ...`
`P6-mrc-isq-hunt.md:28` states the predicate with NO `.xlsx` qualifier: "Sweep predicate over
the url slug (case-insensitive substring): an MRC term [...] AND a population term [...] makes
a url SWEPT".

`run_p6.py:1461` filters to `.xlsx` BEFORE the predicate loop at :1470-1475, so the predicate
never sees the other 22,270 locs. Measured on the live sitemap:
```
locs satisfying the STATED sweep predicate (MRC AND population): 59
   of which .xlsx (actually swept, pre-dedup): 33   -> 22 after slug dedup
   of which NOT .xlsx (NEVER swept)          : 26
   ... 6 of those 26 ALSO satisfy a PROJECTION term, i.e. would be ELIGIBLE, incl.
       /fr/fichier/perspectives-demographiques-des-mrc-du-quebec-2011-2036.pdf
       /fr/produit/publication/mise-a-jour-perspectives-demographiques-mrc-du-quebec-note-methodologique
```
GRADED CARRY, not REOPEN: line 27 names the 3273 `.xlsx` one line above line 28, and the
DECISION token's "(22 matched the MRC×population predicate, 15 eligible)" reads naturally as a
back-reference to §2's computed pair rather than a fresh quantification over 25543. Under that
plain reading nothing is false. The measurement is recorded because it is load-bearing for a
future NOT-FOUND run.
No absence claim rests on it in THIS run (verdict is LOCATED), but on a NOT-FOUND run the
recorded scope would be materially wider than the sweep. Note §2's heading is "ISQ's own
**product pages** / full-edition downloads" while no product page can ever enter the sweep.
Immaterial sub-point (LOW): the note says "over the url **slug**" but `run_p6.py:1471` passes
the FULL url to `_terms`; measured divergence on the live sitemap = 0 locs.

## VERDICT SPLIT — 2 REOPEN / 7 CARRY

**REOPEN (2)** — limb (b), the generated note asserts something false, each with a live measurement:
- **F5** §2's hreflang dedup mechanism is refuted by the document itself: exactly one `<loc>`
  per `<url>` (25705 = 25705), alternates are `xhtml:link href` attributes the regex never
  sees, and only 0.41% of urls repeat — those being cartovista duplicates. An un-deduped count
  would overstate by 0.63%, not the ~2x the stated mechanism implies.
  `P6-mrc-isq-hunt.md:27`, `run_p6.py:373-377`. Mutation M8 SURVIVED (clause unpinned).
- **F6** §3's "a substring test ... counts zero labels below it" — measured **109**, not 0; and
  the real failure mode is a silent wrong-column LOCATED over the `Code` column that
  `_guard_body` passes, not the fail-safe zero-label refusal the note describes.
  `P6-mrc-isq-hunt.md:68`, `run_p6.py:137-141`.
- **F1** §3 promises "the caption and release line below are read from its own bytes and state
  which edition it is" while §3 four lines later states no diffusion date was found.
  `run_p6.py:1066-1068`, unconditional. Mutation M1 SURVIVED.
  (Counted inside the 2 above as the same limb-(b) class; listed separately because it is a
  distinct site and a distinct fix. If the controller prefers per-site counting: 3 REOPEN.)

**CARRY (7)**
- **F2** `test_probe_p6.py:371` DEAD regex — provably unmatchable against any output the
  current generator can produce; plus the false coverage comment at `:862-864`.
- **F3** `test_probe_p6.py:183-184` stale spec quote ("no MRC workbook exists"), amended in `b46692e`.
- **F4** `run_p6.py` docstring "never reproduces its words" vs the §5 emitter that reproduces
  spec §8 verbatim on all four branches.
- **F7** `_ra_membership` aggregate-exclusion branch unreachable; its comment ("the subtotal
  line carries the same RA code as its MRCs") is false — measured `RA1 = None` on all 17.
- **F8** §3b "Every one of the N verified candidates is opened" unconditional vs its own table.
- **F9** `_ra_axis_usable` over-match: a non-code column named "... région administrative" is
  published as a SEPARATE RA column.
- **F10** swept-scope: 26 locs satisfying the note's stated predicate are never swept (6 of
  them would be ELIGIBLE). Immaterial on this LOCATED run; material on a NOT-FOUND run.
- **F11** COVERAGE ASYMMETRY (from mutation M9): the strict set-algebra vocabulary check
  (`test_probe_p6.py:363-369`, `allowed`) runs ONLY on the committed note, which carries the
  em-dash tail form. The fixture path checks `"NOT COMPUTABLE" in named[1]` — a substring test
  that a malformed `_relation_head` still satisfies. So `_relation_head`'s dual-tail handling,
  which its own docstring calls load-bearing, is unpinned on the `(` form that only fixtures
  reach. M9 SURVIVED.

## Re-verified live (recorded values all CORRECT)
GET 200 / HEAD 404 on the located workbook; both guessed slugs 404 on GET; 25543 distinct
locs; 3273 .xlsx; 33 -> 22 slug dedup with all 11 collapses fr/en; 17+105=122; 8+3+4=15 and
the §3b table row counts agree; 6 family matches with 517264 the smallest; §4 marker matches
2 spec lines with §8 first; 122 labels / RA1 = 14,15,16 beside all 10 declared targets.

## Restore verification
`run_p6.py`, `test_probe_p6.py`, `P6-mrc-isq-hunt.md` all byte-IDENTICAL to HEAD (`cmp`).
`git diff --stat` empty. `./scripts/test-all.sh` -> hde 191 + demoflow 74, baseline restored.
