r"""ATTRIBUTION binders for the gates that hold this repo's load-bearing prose.

WHY THIS FILE EXISTS. Several gates protect docstrings and emitted provenance strings that
carry MEASURED figures and the labels those figures belong to. Written as REQUIRED-PRESENT
checks — `assert f"{figure}" in doc` — they are satisfied by three different falsehoods, all
demonstrated GREEN by verifiers on 2026-08-21:

  (i)   TRANSPOSITION — two figures swap the labels they are attached to. Both are still
        present, so every presence assert passes.
  (ii)  OCCURRENCE-SELECTIVE DROP — a required qualifier occurs N times, so dropping the ONE
        occurrence that SCOPES a claim leaves the string present elsewhere.
  (iii) ADDITIVE FALSEHOOD — every true attribution is kept and a FALSE one is added.

All three are evasions of MEMBERSHIP. The cure is the shape operator ruling X7's gate already
uses: bind the figure to the label and assert the binding is FUNCTIONAL — this label maps to
this value, and to NOTHING else. `bound_map` below returns the observed label -> figures
relation so a gate can assert it EQUALS the measured one. One equality closes all three: a
transposition moves a value to the wrong key, a drop empties a key, an addition puts a second
value under a key.

WHY NOT A PROXIMITY WINDOW, measured false-green 2026-08-21 and not to be reintroduced. In
`two sit below it (MTL_ISLAND_RA06 -0.321 pp, LAVAL_RA13 -0.228 pp)` a swap leaves the WRONG
name 1 character from a figure and the right one 38 away, so any window wide enough to admit
`LANAUDIERE_RA14_PROXY +0.035 pp` (22 characters of name) also admits the swap. What is
accepted here is not a neighbourhood but the two WRITTEN FORMS this prose actually uses —
`<label> <figure>` and `<figure> at|for|in|(<label>` — and nothing wider. The BEFORE glue in
particular admits no bare comma: `-0.321 pp, LAVAL_RA13` is a LIST, not an attribution, and a
comma-tolerant glue cross-binds every figure in a list to its successor's name.

WHITESPACE IS COLLAPSED FIRST by `flat`. Every string scanned through here is hard-wrapped
prose, so any figure/label pair is one reflow away from spanning a line break and a raw
substring test would be evaded by the rewrap that editing the prose causes anyway.

THE ONE EVASION THESE BINDERS DO NOT CLOSE ON THEIR OWN, measured 2026-08-21 against this file
rather than assumed: a binder reaches the FIRST figure that sits in an accepted form after (or
before) the label, so an added figure placed BEHIND the true one inside the SAME clause — `(by
-1.078e-06 or by -9.999e-06)` — leaves the map correct and passes. `bound_map` therefore closes
(iii) only for additions that create a NEW label/figure pair. Where the prose puts a whole
clause under one role, gate the clause's CONTENT (`\(by ([^)]*)\)`) or count every figure of
that shape in the document; `tests/test_pipeline.py`'s ED-move gate does both, and the
occurrence-count legs in `tests/test_census_ownership.py` and `tests/test_probe_p10.py` are the
same remedy for the contiguous-clause gates, which cannot see an addition at all.

THE NEGATION CLASS — MEASURED, AND RECORDED RATHER THAN CHASED (seat ruling, 2026-08-21). A
negation inserted AT the claim passes every gate of this shape. `the only two S reads are NOT
the two LEAST contaminated AT SERVED VALUES` satisfies the joined scope-qualifier regex,
satisfies the unscoped-claim forbid pattern's lookahead, and leaves every figure bound to its
label: measured green on the FULL suite with the falsehood shipped through the generator and
the golden re-minted, so the fresh-derivation, byte-for-byte and vintage-hash gates were
satisfied as well. NO FINITE REQUIRED-PRESENT PATTERN CLOSES IT — a negation can be inserted
wherever a claim is asserted, and enumerating its spellings is an arms race a test suite loses,
the more so because every candidate pattern also has to spare the legitimate negations this
prose is full of (`never by households`, `not the bound the argument rests on`, `they do NOT
bracket the rate`). Do not add negation patterns here.

WHAT BOUNDS THAT EXPOSURE, because it is not unbounded. (i) A negation interposed BETWEEN a
label and its figure REDS, measured: `The HIGH corner is NOT exactly ATTAINABLE` breaks the
binding, since the accepted glue admits no words. Only a negation on a claim that carries no
bound figure survives. (ii) The BEHAVIOURAL gates read no prose at all — rulings X1 and X2 are
held by wiring pins and value pins asserted against the model's own numbers — so a negated
docstring cannot make a wrong NUMBER pass. What it corrupts is the RECORD a future reader acts
on, which is why it is stated here in the open instead of left as a silent residual.

THE ADDITIVE RESIDUAL IN THE OCCURRENCE-COUNT LEGS, measured the same day. The counts that
close (iii) for the contiguous-clause gates are PHRASE-EXACT: they count a ROLE PHRASE, so the
same false claim phrased one word differently is neither counted nor seen. Three surfaces
shipped an added falsehood green that way — the sub-25 cell citations in
`tests/test_census_ownership.py` (an added cell written `owners among` rather than `owners
of`), the `isq_territory_note` person roles in the same file (an added figure written without
the role's parenthetical), and the separability token in `tests/test_probe_p10.py`. WHERE THE
FIGURE SHAPE IS EXACT, COUNT THE SHAPE IN THE SURFACE rather than the role phrase: both census
sites now do, because `'\d+ to \d+ years'` occurs there in five known roles and `[\d,]+
persons` in exactly two. The P10 token is RECORDED, NOT CLOSED: its two means are bare `[\d,]+`
in a sentence that also states `8 regional rows`, `within 3/yr` and `footnote: 2`, so no figure
shape separates the means from the prose around them and a count of the loose shape would be a
literal no reader could check.

THE UNGATED OPERAND PAIR, ACCEPTED (seat ruling, 2026-08-21). `pipeline._standing_stock` writes
each offset beside the two rates it is the difference OF — `-0.162 pp at MTL_RMR
(0.5599109544965435 against 0.5615325746167329)` — and that RAW PAIR is ungated: transposing the
two operands ships the full suite green, because every binder here reads a `pp` or `%` shape and
a bare seventeen-digit float carries neither. It stays open deliberately. The pp figure the pair
supports is bound to its ROW and to its ROLE (the region legs in `tests/test_pipeline.py`), so
the sign and the size of the difference are gated; the operands are supporting detail, and their
transposition reverses the ORDER of a subtraction whose result is already pinned — which is why
the recorded history of that gate can already name the shape ("self-contradictory on its own
line"). A binder for a bare float shape in this prose would bind every product id, member count
and threshold beside it. THAT PIN IS MEASURED, not assumed: flipping `-0.162 pp` to `+0.162 pp`
in BOTH documents reds on the per-row map in
`tests/test_pipeline.py::test_x1_the_docstrings_QUOTE_the_computed_narrowing_and_offset_figures`,
which reports `['+0.162 pp', '+1.073 pp']` against a measured `['+1.073 pp', '-0.162 pp']`. So
the difference the operands support cannot change sign or size unnoticed; only the ORDER of the
two numbers it is formed from is free.

EXACT-CLAUSE RIGIDITY IS BY DESIGN, ACCEPTED (same ruling). Several gates require a clause
VERBATIM, so a truth-preserving re-word reds. Three were measured on 2026-08-21: `each` ->
`every` inside the narrowing region's opening anchor (`role_regions` in
`tests/test_pipeline.py`), "at `85+`, whose" -> "at the `85+` band, whose"
(`tests/test_hors_aligned_ownership.py`), and "which is the CENSUS-NET" -> "which is in fact the
CENSUS-NET" (the retired-figure clause). That is a real cost and it is accepted, because it is
ANTICIPATED AND SELF-DOCUMENTING rather than silent: each failure message names the clause it
wants and tells the author to RE-SITE the leg rather than widen it. The region guard's
`0 <= start < end` is deliberately part of that — a `find` that misses returns -1, and a region
sliced from -1 is a gate that cannot fail, so the strictness is buying a leg that can fail. A
rigid clause costs one edit; a slice from -1 costs the whole leg.

THE SELF-CONTRADICTORY CLASS, ACCEPTED (seat ruling, 2026-08-21). Where a sentence states a
DIRECTION beside the SIGNED FIGURES that entail it, flipping the direction word alone leaves the
figures bound to their names, so the sentence refutes itself instead of asserting a falsehood the
record elsewhere supports. The measured instance is `_standing_stock`'s straddle sentence: "two
sit below it (MTL_ISLAND_RA06 -0.321 pp, LAVAL_RA13 -0.228 pp) and THREE sit ABOVE —
LANAUDIERE_RA14_PROXY +0.035 pp, ..." — flipping ABOVE to BELOW ships green, because every row's
signed pp figure stays bound to its own name by the per-row map and by the role-region legs, and
the straddle ruling therefore survives ARITHMETICALLY: a reader meets three positive figures
under the word "below" and can see which half is wrong. A gate here would have to require the
direction word beside a set of figures whose SIGNS already state it, which is a second spelling
of a leg that already exists. The line this class does NOT cross is the one item 3 of run 46 was
about: where the direction word is the ONLY statement of the ordering and no figure beside it
contradicts the flip, it is gated (the served-interval clause, the envelope's worked example).

THE POLARITY-WORD CENSUS, RE-DERIVED AND CLASSIFIED (run 47, 2026-08-21, replacing run 46's
"roughly a dozen" — an ESTIMATE standing where the paragraph claimed a COUNT, which is the
defect class this whole surface exists to close, so it is re-derived here rather than repaired
by rounding). The four load-bearing prose surfaces — `pipeline._standing_stock.__doc__`,
`hors_aligned.__doc__`, `hors_aligned._SUPERSEDES` and `MODEL_CHOICE_PROVENANCE["roll_age"]` —
carry THIRTY occurrences of below/above/lower/higher/falls/rises between them (11 / 12 / 4 / 3,
enumerated mechanically over the flattened text, not read off). THE CLASSIFICATION RULE, applied
to each one: invert that SINGLE word to its polar opposite, leave every other byte alone, and
ask what the resulting document then asserts. The measured split — one mutate/run/restore cycle
per occurrence, against the SIX test files that read these surfaces
(`test_hors_aligned_ownership.py`, `test_probe_p10.py`, `test_constants.py`,
`test_artifacts.py`, `test_golden.py`, and `test_pipeline.py`'s four prose tests):

  17 GATED. A CLAIM gate reds on the bare inversion. Sixteen already did; the seventeenth is the
     suppression bound below, which run 46 left open and run 47 closed.
   1 REGEN-SHADOWED. `_SUPERSEDES`'s "returns 0.0 below OWNERSHIP_LATTICE_FLOOR 25". Its bare
     inversion reds `test_p11_5_committed_artifact_equals_a_fresh_derivation`,
     `test_p11_6_the_generator_reproduces_the_committed_artifact_byte_for_byte` and
     `test_p11_20_...` — because the string is EMITTED, never because a gate reads the claim.
     That last part is MEASURED, not inferred: regenerating through `gen_hors_aligned.py` and
     re-minting the golden ships the falsehood on a FULL GREEN suite (1190 passed). The SAME
     sentence in the module docstring, which nothing emits, is green with no regeneration.
   9 NON-CLAIM, green. FIVE document navigation ("the slice below is every age >= 75", "Reason
     (iii) below already ENTAILED that", "`_band_entry_stock` below is unaffected", "the
     envelope below is one-sided", "see the history paragraph above"); TWO retired wordings
     QUOTED AS HISTORY (the phrase "systematically BELOW" that stood here, and the run-25
     record's "the feasible maximum +0.251% sat above the diagonal pair's +0.223%"); TWO code
     facts pinned at their own site in un-emitted prose ("`demand/formation._ownership` returns
     0.0 below `OWNERSHIP_LATTICE_FLOOR` 25", "It does not extend the curve below 25").
     Inverting any of the nine yields a broken cross-reference, a misquoted history or a
     misstated code fact — never a false model claim — and a binder that reached them would
     fire on all thirty.
   3 green in the straddle sentence, and they are NOT one bucket — 2 SELF-CONTRADICTORY
     plus 1 NON-SEQUITUR (re-measured 2026-08-22). The two that earn the label are the row
     placements: "two sit BELOW it (MTL_ISLAND_RA06 -0.321 pp, ...)" and "THREE sit ABOVE —
     LANAUDIERE_RA14_PROXY +0.035 pp, ...", where the signed figures beside the word refute the
     flip on the same line. The THIRD is "the new spread ... straddles 0.5615325746167329, so
     some row is ABOVE it by arithmetic": flip that ABOVE to BELOW and the sentence is simply
     TRUE — a straddle entails rows on BOTH sides — so it states a truth that no longer supports
     the point it is offered for. That is a NON-SEQUITUR, not a contradiction a reader can catch
     by comparing the word to figures beside it. The COUNT is unchanged at 3 and so is the
     protection claim; what changes is that one of the three is caught only by noticing an
     argument that does not land, which is weaker than the two that self-refute.

THE EVIDENCE TIER BEHIND THAT SPLIT, said rather than implied. The seventeen REDS are targeted-run
reds, and a red anywhere is a complete proof of gatedness. Of the greens, the suppression bound
(a) below was measured green on the FULL suite alone; the other TWELVE were measured green
individually on the targeted subset AND jointly on the full suite — one run with all twelve
inversions applied at once. A joint green is weaker than twelve separate full runs wherever a
gate could compare two mutated regions, so it is named as joint here instead of being reported
as twelve.

WHERE THIS COUNT PARTS FROM THE PREVIOUS VERIFIER'S, stated rather than split. That verifier
measured 16 gated / 3 self-contradictory / 1 unaccounted, and 10 non-claims (5 navigation,
2 quoted history, 3 code facts). The gated count, the self-contradictory count and the single
unaccounted item agree EXACTLY. The one difference is the third code fact: it is the EMITTED
copy at `_SUPERSEDES`, and its bare inversion is not free — three gates red on it — so it is
named here as regen-shadowed instead of being counted among the nine that cost nothing. Nothing
moves in or out of a load-bearing bucket. Gating is spent where the word IS the finding, and
that remainder is now ENUMERATED rather than estimated.

WHAT RUN 47 CLOSED. Each was measured GREEN on the full suite BEFORE its gate was written, and
red after it:

  (a) `hors_aligned.__doc__` — "Each withheld field is bounded ABOVE by a quantity the same cube
      DOES publish". Flipping ABOVE to BELOW shipped the FULL SUITE GREEN (1187 passed), and
      that word is the premise of the four-corner envelope, of `aligned_bound_rate` being the
      subtract-MOST corner, and of `SUPPRESSION IS BOUNDED, NEVER DROPPED`. Held now in BOTH
      copies that state it — the docstring, and the emitted `suppression.bound`'s "FIELD-WISE
      upper bound", which was ungated too — from ONE test-owned direction, beside three numeric
      legs (the charge is non-negative, strictly positive somewhere, and the two DIAGONAL
      corners sit inside the OFF-DIAGONAL envelope at every band). THE THIRD LEG IS THINNER THAN
      IT READS, measured 2026-08-22 rather than left to the word "inside": it is satisfied by
      EQUALITY at 6 of the 7 bands. Five of them (25-34 through 65-74) charge (0, 0), so the
      envelope collapses to a single point and the diagonal pair IS that point; at 75-84 the
      envelope endpoints equal the diagonal pair exactly. Only 85+ is strictly interior, with
      slack about 7.74e-04 on each side. The leg is TRUE as written and it still fails on a
      charge that stops bounding the cell — but on this vintage it is carried by ONE band, and a
      reader who took "at every band" for seven independent margins would be over-reading it. The direction
      word itself is NOT derivable from the artifact — the unpublished remainder is the same
      number under either reading of it — and that test says so in its own docstring instead of
      dressing a constant up as a derivation. Gate:
      `tests/test_hors_aligned_ownership.py::
      test_the_withheld_field_bound_states_WHICH_DIRECTION_it_bounds_in`.
      WHAT A BARE EDIT OF THE EMITTED COPY REDS, counted rather than assumed (2026-08-22):
      flipping `FIELD-WISE upper bound` to `lower` in `data/ownership_hors_aligned.json` alone
      reds FIVE tests, not the three a reader would predict from the source-mutation cases in
      the named-open list below — this gate, `test_p11_5`, `test_p11_6`, AND BOTH
      `tests/test_golden.py` tests (`test_rankings_match_golden`,
      `test_tripwire_baseline_matches_golden`). The extra two are the difference between editing
      a COMMITTED INPUT and editing SOURCE: this file is an input the golden's fresh derivation
      reads, so `artifacts/rankings.json` and `artifacts/tripwire_baseline.json` stop matching
      too, whereas a prose mutation in `hors_aligned.py` moves only the FRESH artifact and reds
      exactly three (measured the same day on item (4) below: 3 failed, 1187 passed). Worth
      distinguishing because it decides whether a regeneration is PR-visible in two files or in
      four.
  (b) `pipeline._standing_stock.__doc__` — the min-pairing theorem `sum_a min(m_a, f_a) <=
      min(sum m, sum f)`, which NO test in this suite mentioned. `>=` shipped the FULL SUITE
      GREEN at one character, inverting the theorem that is the entire reason per-age summation
      (arm D) is rejected rather than adopted as a finer version of this repair. It is gated
      NUMERICALLY and not as a string: both sides are rebuilt from the model's own base-year 75+
      slice — population by age and sex, the collective share, and the living-arrangement reads
      AT EACH AGE — paired through `match_couples` itself, the STRICT gap is measured at all
      EIGHT geographies (MTL_RMR 64331.1 against 64427.2, QC_RMR 16100.0 against 16179.1, and so
      on), and the operator in the prose is DERIVED from that measurement. Strictness is the leg
      that refutes `>=`: `<=` is satisfied by equality too, and equality is what a suite passes
      vacuously. A theorem gated only as a string is still only prose. Gate:
      `tests/test_pipeline.py::
      test_the_min_pairing_theorem_ARM_D_IS_REJECTED_ON_is_STATED_and_HOLDS`.
  (c) `pipeline._standing_stock.__doc__` — ruling X4's channel attribution, "min-pairing is only
      1.3-8.9% of the gap and the LA re-read is 73.9-100.3% of it". Transposing the two spans
      restored EXACTLY the matching-dominated mislabel X4 was issued against, with both spans
      still present — measured on the full suite with the new gate as the ONLY red, 1189 of the
      1190 tests passing on the transposed prose, which is the state run 46 shipped. The spans
      are now bound to their channels, one each, and required DISJOINT with min-pairing's
      entirely BELOW the LA re-read's — X4's finding as an inequality rather than as four digit
      strings, so a legitimate refresh that moved both spans consistently stays green. The
      two MTL_RMR moves the same sentence hangs on them (-18.72% from the LA
      re-read, -0.149% from per-age matching) were unbound as well and are now bound to their
      channels with the same ordering. WHAT IS NOT GATED THERE: the span ENDPOINTS. This suite
      does not run the arm-D decomposition, so those four figures are the paragraph's own
      measurement and no leg re-derives them. Gate:
      `tests/test_pipeline.py::
      test_x4_the_two_CHANNELS_of_the_per_age_gap_keep_their_own_RANGES_and_their_ORDER`.

WHAT IS NAMED-OPEN, deliberately (seat ruling, run 47) — with the one-line mutation that reaches
each one, so a future reader can act without re-deriving it. Every one re-verified GREEN against
the FINAL suite: the three plain residuals on the full 1190-test run, the two pairs
through the generator.

  (1) `hors_aligned.py:48` — "concentrates in 25-34, the MOST contaminated of the seven" ->
      LEAST. The D half of the adverse-arrangement argument. Its contradiction — the range
      "+0.242% (75-84) to +3.559% (25-34)", both figures bound to their bands — sits three
      sentences away rather than beside the word, which is weaker than the straddle sentence's.
  (2) `hors_aligned.py:38` — "is AMPLIFIED rather than averaged" -> "is averaged rather than
      AMPLIFIED". States the exact premise amendment #12(B)'s reversal was issued against.
  (3) `pipeline.py:951` — "a QUARTER of the 2.593 pp defect being repaired" -> "a HALF". The leg
      that checks the quantity asserts `0.20 <= qc_share <= 0.30` and never reads the prose, so
      the WORD is free. A false MAGNITUDE rather than an inverted polarity, which is why it
      ranks last of the three.
  (4) REGEN-SHADOWED, x2: `hors_aligned.py:50` + `:300` — "most heavily WEIGHTED" -> least. This
      one lands in the PUBLISHED record. A bare mutation reds the twin-equality trio; green
      needs a DELIBERATE regeneration, which is PR-visible as artifact byte changes. Measured
      both ways: the bare mutation reds `test_p11_5`, `test_p11_6` and `test_p11_20`, and after
      `gen_hors_aligned.py` then `gen_golden.py` the full suite is GREEN (1190 passed) with
      THREE files moved — `data/ownership_hors_aligned.json`, `artifacts/rankings.json` and
      `artifacts/tripwire_baseline.json`. The PR diff is the only reader left.
  (5) REGEN-SHADOWED, x2: `hors_aligned.py:39` + `:340` — "negative for D < S" / "NEGATIVE for
      D < S" -> "D > S", the sign condition on the D/(D-S) amplifier. Same shape as (4), and
      measured the same way — same three reds bare, the same three files moved, GREEN at 1190
      after regeneration.

AND TWO MESSAGE-LEVEL ITEMS THAT ARE RIGIDITY RATHER THAN HOLES, recorded so the next reader
does not mistake the cost for a defect. `tests/test_pipeline.py`'s four `role_regions` anchors —
two verbatim sentence openers and two closers, across two documents — so reorganising the X3
paragraphs reds four legs at once; and `tests/test_hors_aligned_ownership.py`'s `counts_clause`,
which requires "aligned household counts 110,150 / 30,605, is +0.244%" as one contiguous span
down to the thousands separators. Both cost an author ONE edit, both messages quote the clause
they want, and each says RE-SITE rather than widen — so the instruction can be followed, which
is the whole line between this paragraph and the one below it.

THE FORBID CENSUS, ENUMERATED AND CLOSED (run 48, 2026-08-22) — the mirror image of every
paragraph above, which hardens REQUIRED-PRESENT checks and left FORBIDS untouched. THE
POPULATION WAS ENUMERATED, NOT SAMPLED: 194 forbid sites across all 47 files under `tests/`,
found by parsing every file's AST — 92 with a string-literal left operand or a `not re.*` call, 101
whose left operand is a variable or expression (the forbid LISTS, plus structural membership
over dicts and sets), and 1 compiled-pattern list that NEITHER AST shape reaches and only grep
found (`tests/test_owner_stock.py`'s three `inflat|deflat` patterns, which were already
`re.IGNORECASE`). Each was classified by EXECUTION — load the real surface, inject the
forbidden claim in emphasis capitals, evaluate the forbid predicate — not by reading.

45 LITERALS ACROSS 26 SITES WERE CASING- OR WHITESPACE-EVADABLE, and all 45 are closed: 25
substring forbids now route through `says` above, 20 regex forbids carry `re.IGNORECASE`. The
26 is DERIVED from the diff, not counted by hand — every changed line carrying a widened forbid
predicate, with `test_pipeline.py`'s `unscoped` findall counted ONCE because it appears on both
the assert and its own message line.

THE EVIDENCE TIER, said rather than implied. Every one of the 26 SITES has a MEASURED red:
mutate the real surface, run the node, restore under `cmp` plus sha, and pair it with the
OLD-predicate green evaluated on the SAME bytes — so each is an evasion demonstrated closed and
not a widening asserted. WITHIN the nine sites whose forbid is a LOOP over several literals
(the six-member mechanism list, the four retired forms, the three unscoped patterns, and so on)
one literal was driven as the REPRESENTATIVE and the rest were classified at the predicate
level, which is exact for a substring or regex test but is not 45 separate suite reds. THE
NO-TAX DIRECTION WAS PROVED FIRST, not afterwards: the full suite ran with all 45 widened
forbids against the RATIFIED bytes before any of them was trusted (191 + 1190 passed), and that
is what shows the quoted history and attributed wordings this corpus keeps on purpose stay
legal — including `hors_aligned.__doc__`'s four-band history paragraph and the retired-figure
clause it quotes.

WHAT NEEDED NO CHANGE, said so it is not churned later. Forbids whose subject is a MACHINE
TOKEN from a closed emitter vocabulary (`LIVE PROBE FAILED`, `[FILL`, `NOT CORROBORATED`,
`NOT CHECKABLE`, `NOT COMPUTABLE`, every `DECISION-*` value, the `UNRESOLVED` sentinels which
are already `.upper()`-normalised at every call site), a CODE IDENTIFIER (case-significant to
Python, so the casing is not an author's choice), a dict or set KEY, or a digit/symbol-only
literal. Their casing is fixed by the code that computes them, and their sibling legs compare
them by equality or `startswith` against the same vocabulary — so widening buys nothing.
Already case-insensitive before this run and left alone: `test_pipeline.py`'s
`at or near the full spread`, `test_probe_p8.py`'s `does not exist`, `test_tripwires.py`'s
`member-set truncation`, and the `test_owner_stock.py` triple.

WHAT THIS CENSUS STRUCTURALLY COULD NOT SEE, and none of it is closed by casing. A forbid
evaded by a SYNONYM or a re-word rather than a re-casing — the same arms race THE NEGATION
CLASS above is recorded for, and refused for the same reason. Forbids living OUTSIDE
`tests/**`: the probe scripts and the `LoaderError` raises hold their own negative checks and
were not enumerated. And one adjacent hole this census met and did NOT fix, because it is a
different class: `tests/test_demand.py`'s `"loaders.isq" not in text` is a source-text proxy for
import reachability, and `from demoflow.loaders import isq` satisfies it while importing the
module — a SPELLING gap, not a casing gap, and widening it is a separate job.

WHAT BOUNDS EVERY PARAGRAPH ON THIS PAGE, and it is the honest ceiling on the entire prose
surface: THE BEHAVIOURAL GATES READ NO PROSE. Rulings X1 and X2 are held by wiring pins asserted
at the call argument; the eight `mean_ed_reference` values and the standing rates are held by
value pins; the golden is re-derived and compared; all SEVEN `data/*.json` and both
`artifacts/*.json` are held byte-identical, and `assumptions_hash` is pinned. None of those
reads a docstring. So a flipped direction word — gated, accepted or open — CANNOT make a wrong
NUMBER ship. What every residual on this page corrupts is the RECORD a future reader acts on.

ONE SURFACE IS NOW AN EXCEPTION TO THE SENTENCE ABOVE, and it is worth naming because the
sentence used to be unqualified: `artifacts/README.md` is the shipped CONSUMER contract, not a
docstring, and `tests/test_golden.py` reads it in MARKED SPANS — the current-state claims
against the shipped bytes AND against `constants.assumptions_hash()` itself, the raw-anchor
disclosure against a filesystem measurement, the sweep counts and axis roster against the
declared grid, and the THREE NAMED LIMITS spec amendments #20 and #24(A) declare as a functional
role -> figure map, an ORDERED CENSUS of EVERY figure shape they state — ratio, exponential,
multiple, rank-movement glyph, PERCENT and PERCENTAGE-POINT — and each limit's instrument and
its reorder bound to the PARAGRAPH that states it rather than to the span, exclusively over every
ordered pair of the three, plus its CLASS (measured, or constructed bound) WHERE THE PAGE STATES
ONE, which is two of the three: (B)'s paragraph carries no class phrase, so that roster is smaller
than the limit roster on purpose and its exclusivity runs over the pairs it has. THE LAST TWO SHAPES ARRIVED
LATE AND THIS SENTENCE NAMED THEM BEFORE THEY WERE HELD: amendment #24(A) introduced percent and
pp figures — limit (C)'s threshold and its comparison to the level fix — and the word EVERY here
was false for one round while all three were resizable under a same-edit digest re-mint with the
full file green. Widen the censuses when a shape arrives, or narrow this word; a completeness
claim standing where the code has a hole is the exact damage this file records at `_LIMIT_MOVEMENTS`.
HOW MANY SPANS THERE ARE IS DELIBERATELY NOT WRITTEN HERE: the page states its own count and
`test_the_readme_binds_its_OWN_count_of_marked_spans` measures that word against the markers, so
a second copy of the number in this file would be a staleness generator holding nothing — which
is precisely what the copy this sentence used to carry had become. `assumptions_hash`
was pinned as a VALUE and never against its PROSE copies; a stale token on that page now REDS,
and a superseded token is required to sit under a heading that says HISTORY. That page is
Tranche-1-blocking by the amendment's own words ("a limit declared only in a spec the consumer
never opens is undeclared"), which is why it is gated and the docstrings are not.
That is a real cost, and it is the reason any of this gating exists; it is not a correctness
hole in the model, and a run record that implied otherwise would be overstating this file the
way run 46's coverage sentence overstated it.

WHAT IS NOT ACCEPTED, and the line between the two is the whole point: a gate whose FAILURE
MESSAGE PRESCRIBES a wording the gate itself rejects. THREE existed and all three are closed
(2026-08-21). The 85+ share's denominator required the bare "of the block" while its own message
spelled the denominator out as "of the 75+ block", so making the prose MORE precise — exactly
what the failure text asked for — red, permanently. Run 46 then introduced a second: the
`roll_age` asymmetry gate labelled S's half `r"the S"` while its message states the claim as
"S's NUMERATOR valued the same households through one band read", so an author who wrote the
possessive got `halves["S's half"]: set()` — measured, and a PERMANENT red for obeying the
instructions. The third was found by run 47's sweep of every message runs 43-46 added: the
"materially lower rate" gate renders the claim in its own first sentence as "own at a materially
LOWER rate", the emphasis capitals this prose uses everywhere, and writing exactly that RED
(measured). A cost an author can read and pay is documentation; a cost whose instructions cannot
be followed is a trap. All three now accept the two written forms of ONE word and NOTHING wider
— `higher` in either casing, any other denominator, any other subject still reds, which is the
falsehood each leg exists for. THE SWEEP THAT FOUND THE THIRD is recorded because it is the
MOTION and not the catch, and its three stages are named separately because a sweep described as
wholly mechanical would claim more than ran: every assert message in the SIX prose-bearing test
files (`test_pipeline.py`, `test_hors_aligned_ownership.py`, `test_census_ownership.py`,
`test_probe_p10.py`, `test_probe_p3.py`, this file) was PARSED mechanically and every quoted
prose span of four words or more checked against its own assert's literals; the flagged spans
were TRIAGED by reading; and the live candidates were MEASURED by writing the prescribed form
into the source. Two rigidity items survived that triage and are named in the named-open
paragraph above as rigidity rather than holes.
"""

import re

# The figure shapes this prose states. Each is a whole regex, used as a capture body. SIGNED
# and PLAIN percentages are kept APART on purpose: a band label carries both a signed
# contamination (+0.253%) and an unsigned share of the block (24.147%), so one pattern for both
# would report two values under one label and make the equality unreadable.
PCT_SIGNED = r"[+-]\d+\.\d+%"             # +0.242%
PCT_PLAIN = r"(?<![+\-\d.])\d+\.\d+%"     # 24.147%, and never the tail of +0.253%
PP = r"[+-]\d+\.\d+ pp"                  # -0.321 pp
PP_ABS = r"(?<![+\-\d.])\d+\.\d+ pp"     # 0.0029 pp
# THE `e` IS CASE-INSENSITIVE (run 53). This corpus's house style is EMPHASIS CAPITALS, so
# `-2E-03` is the spelling an author here actually reaches for, and the lower-case-only pattern
# let it past the ordered exponential census on `artifacts/README.md`'s named-limits span —
# measured GREEN on the full suite with the content digest updated in the same edit, which is
# precisely the attack that census exists to survive. `[eE]` rather than `re.IGNORECASE`: the
# lookarounds are lower-case hex on purpose and folding them would widen the guard too.
# MEASURED: `findall` is byte-identical to the old pattern's on every `.py` file in this tree
# and on `artifacts/README.md`, except two COMMENTS that quote an uppercase form as a recorded
# evasion — neither of them a surface any binder scans — so no bound figure and no quoted
# history moved.
#
# THE DECIMAL POINT WAS REQUIRED AND IS NOW OPTIONAL (run 52). `\d+\.\d+e` cannot see
# `-2e-03`, so an ADDED exponential figure written without a fractional part evaded every
# ordered-census leg built on this shape — measured GREEN on the full 1226-test suite with
# `a rebound of -2e-03 per row` appended to `artifacts/README.md`'s named-limits span, which is
# the one surface whose exponential census is the addition-proof remedy for a RANGE. The
# lookarounds are what make the widening free rather than a new false-positive source: without
# them `\d+e[+-]?\d+` matches INSIDE a 64-hex digest (`…b815e7263c…` yields `815e7263`), and
# the leading guard also refuses the digit run after a decimal point. MEASURED: `findall` is
# byte-identical to the old pattern's on all three surfaces these binders scan
# (`artifacts/README.md`, `pipeline._standing_stock.__doc__`, `hors_aligned.__doc__`), so no
# quoted history and no legitimate figure moved.
EXP = r"(?<![0-9a-f.])[+-]?\d+(?:\.\d+)?[eE][+-]?\d+(?![0-9a-f])"    # -1.078e-06, and -2e-03

# `<label> <figure>`: at most two spaces/commas, then an OPTIONAL opener or short copula.
# "75-84 (+0.242%)", "MTL_ISLAND_RA06 -0.321 pp", "45-54 at +0.273%", "= +2.243%".
AFTER = r"[\s,]{0,2}[(\[]?(?:at |is |of |= )?"
# `<figure> at|for|in|(<label>`: an EXPLICIT connective is required. A bare comma is a list
# separator in this prose, never an attribution, so it is not glue.
BEFORE = r"\s?(?:at |for |in |\()"


def flat(text: str) -> str:
    """Whitespace collapsed to single spaces — see the module note."""
    return " ".join(text.split())


def says(text: str, phrase: str) -> bool:
    """Whether `text` STATES `phrase` — CASE-FOLDED and whitespace-collapsed on both sides.

    THE FORBID SIDE OF THIS FILE, and the exact mirror of the presence gates above (run 48,
    2026-08-22). Everything up to here hardens REQUIRED-PRESENT checks. A FORBID has the
    opposite failure mode and it was untouched by that work: `assert "only mechanical trigger"
    not in text` is CASE-SENSITIVE inside a corpus whose house style is EMPHASIS CAPITALS, so
    an author writing "that tripwire is the ONLY MECHANICAL TRIGGER and the only guard that
    reds on ANY move" satisfies the forbid AND the scope leg beside it and ships the FULL SUITE
    GREEN. MEASURED FIRST-HAND, 2026-08-22, and the method matters because the claim is a GREEN:
    an isolated tree built by `git archive` at the PRE-FIX gates, that sentence written into
    `demand/formation.py`, demoflow suite 1190 passed. The casing is not exotic: it is the
    casing that gate's OWN FAILURE MESSAGE renders the claim in. A guard that misses the spelling its subject is
    actually written in reads as protecting something it does not protect.

    WHY BOTH AXES, AND NOTHING WIDER. Case folding closes the emphasis variant; the whitespace
    collapse closes the hard-wrap variant, which is the same evasion `flat` exists for on the
    presence side — these forbids scan hard-wrapped prose and `#`-commented blocks, so any
    phrase is one reflow away from spanning a line break. It stops there ON PURPOSE: no
    stemming, no synonym set, no negation patterns (see THE NEGATION CLASS above). A forbid
    widened past the written FORMS of one phrase starts reddening on the QUOTED HISTORY this
    corpus keeps deliberately, and a gate that cannot let the record say what it used to say is
    worse than the hole it closes.

    WHERE CASING IS THE WRONG DISCRIMINATOR, and the one measured instance is recorded because
    it is the boundary of this helper rather than an exception to it: `tests/test_pipeline.py`'s
    retired-form list carries "S reads the TWO LEAST", whose LIVE and correct successor in
    `hors_aligned.__doc__` is "S reads the two least contaminated AT SERVED VALUES" — the same
    words, lower-cased and SCOPED. Case-folding that one literal reds on the sentence the
    record is supposed to say. Its discriminator is the SCOPE QUALIFIER, so it is written there
    as a lookahead pattern and NOT routed through here. Ask what separates the live claim from
    the quoted one before reaching for this function.
    """
    return flat(phrase).casefold() in flat(text).casefold()


def figures_bound_to(text: str, label: str, figure: str,
                     *, after: str | None = AFTER, before: str | None = BEFORE) -> set[str]:
    """Every `figure` the text states BOUND to `label`, in the two written forms above.

    `label` and `figure` are regexes; `label` names the ROLE the figure plays, which is not
    always a proper name — "alone rises to" is the label of the envelope-high corner figure.
    Either glue may be None where the prose never writes that form; narrowing the accepted
    forms only ever makes the gate stricter."""
    s = flat(text)
    patterns = []
    if after is not None:
        patterns.append(rf"(?:{label}){after}(?P<fig>{figure})")
    if before is not None:
        patterns.append(rf"(?P<fig>{figure}){before}(?:{label})")
    assert patterns, "a binder with neither written form accepts nothing"
    return {m.group("fig") for pattern in patterns for m in re.finditer(pattern, s)}


def bound_map(text: str, labels: dict[str, str], figure: str, **glue) -> dict[str, set[str]]:
    """{label name: the set of figures bound to it} — the relation a gate asserts EQUALS the
    measured one. The label universe is CLOSED by the caller: exclusivity is set-equality over
    the labels the gate declares, never "this figure appears nowhere else in the document",
    which would red on a legitimate second mention in a different role."""
    return {name: figures_bound_to(text, pattern, figure, **glue)
            for name, pattern in labels.items()}
