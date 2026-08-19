# Stress-tester audit (pre-PR gate) — demoflow Tranche 1

- run: `wf_19bc200b-298`, gate `stress`, agent type `mm-spine:stress-tester`
- date: 2026-08-19; code tree as of `aaf8e1f` (hde 191 + demoflow 1097, seat's own gate run)
- **VERDICT: PROCEED-WITH-MODIFICATIONS** — dry: `False` (10 findings)

This gate was RE-AIMED by the seat: the SPEC governs (amendments #7–#16, rulings A–U), the
plan is historical, and every plan-vs-tree divergence is classified rather than reported flat.
The agent wrote nothing; this document is the seat's record of its returned verdict.

## Findings

### F1 — [CRITICAL / code-defect / DECISION-CRITICAL]

**Claim.** `rank_stable: true` ships on all 8 rankings rows as a verdict over ONE of FIVE declared robustness axes. The unwired immigrant-ownership-ratio axis REORDERS the published ranking at BOTH of its endpoints, so the spec-mandated sweep would return `false` for several geographies (including rank 1) on the committed vintage.

**Evidence.** GRID vs CODE: `grep -rn 'SWEEP_GRID\[' src/ --include=*.py` returns exactly one executable hit, demoflow/src/demoflow/pipeline.py:890 `lo, hi = SWEEP_GRID["q_live_per_year"]`. The declared grid is constants.py:234-239 (q_live_per_year, phi_voluntary, estate_eventual_fraction, estate_lag_years) PLUS constants.py:199-206 `immigrant_ownership_ratio_sweep_span = (0.155, 1.033)`, which has ZERO readers in src/ (grep returns only its own declaration plus three comments).
EXECUTED PROBE (/tmp/claude-1000/.../st-run-a/mutroot/demoflow/probe_sweep.py; committed data_dir, central q_live, `_ed_series` re-derived per leg, `rank_geographies` unchanged):
  shipped order = [HORS_RMR, LAURENTIDES_RA15_PROXY, LANAUDIERE_RA14_PROXY, LAVAL_RA13, MONTEREGIE_RA16_PROXY, MTL_RMR, QC_RMR, MTL_ISLAND_RA06]
  SWEEP_GRID[q_live_per_year] lo=0.06 / hi=0.11 (the ONE axis wired) -> order UNCHANGED
  SWEEP_GRID[phi_voluntary] 0.7 / 1.0 (NOT WIRED) -> order UNCHANGED
  SWEEP_GRID[estate_eventual_fraction] 0.6 / 0.85 (NOT WIRED) -> order UNCHANGED
  SWEEP_GRID[estate_lag_years] 1 / 3 (NOT WIRED) -> order UNCHANGED
  ratio override hi=1.033 (NOT WIRED) -> *** ORDER FLIPPED *** [HORS_RMR, LAURENTIDES, LAVAL_RA13, LANAUDIERE, MONTEREGIE, MTL_RMR, MTL_ISLAND_RA06, QC_RMR] (ranks 3/4 and 7/8 SWAP; 1.033 sits INSIDE the shipped per-geography ratio range 0.891-1.111, so this half is not an artifact of the uniform-override construction)
  ratio override lo=0.155 (NOT WIRED) -> *** ORDER FLIPPED *** [LAVAL_RA13, MTL_RMR, MONTEREGIE, HORS_RMR, MTL_ISLAND, LAURENTIDES, LANAUDIERE, QC_RMR] (complete reorder; rank 1 moves HORS_RMR -> LAVAL_RA13)
SHIPPED ARTIFACT: demoflow/artifacts/rankings.json carries "rank_stable": true on all eight rows.
CONTRACT ANCHORS, all post-plan and none amended to match: spec:888-889 (7b run contract) "band ENDPOINTS enter only through the mandated robustness sweep, reported per geography as a rank-stability flag (does the ordering change ANYWHERE IN THE SWEEP GRID?)"; spec:549 (amendment #12(C)) rests its containment argument on "Task 29's uniform ratio override spans [0.155, 1.033]"; constants.py:229-232 states the override as an existing fact of Task 29; tests/test_constants.py:186 comments "the endpoints Task 29's override must read". Task 29 IS pipeline.py.
WHY NO TEST CATCHES IT: tests/test_pipeline.py:850 `test_rank_stable_covers_every_ranked_geography` asserts GEOGRAPHY coverage and bool TYPE, never AXIS coverage. The narrowing is declared only in a docstring line (pipeline.py:23 "the sweep varies q_live alone"), which is not a spec amendment. rankings.py:150-156 states the obligation the tree then under-meets: "a run that ships `rank_stable: true` without sweeping is claiming a verification verdict it never computed."

**Fix.** Wire the four unwired legs into `_rank_stability` (pipeline.py:873-892): the other three SWEEP_GRID axes via cohort/listings.py's three read-through bindings, and a uniform join-table ratio override at both endpoints of CONSTANTS["immigrant_ownership_ratio_sweep_span"]; then re-mint the golden - several rows correctly becoming `rank_stable: false` IS the right outcome, not a regression. Add a test asserting the swept-axis set equals the declared grid, so a future axis added to the constant cannot go unswept. ALTERNATIVELY (seat's call, spec-side): amend 7b to scope the verdict to the q_live axis and rename/qualify the emitted field. Do not leave `rank_stable: true` standing under the current contract.

### F2 — [MED / code-defect / DECISION-CRITICAL]

**Claim.** Two uncited model literals on the money path each swing the SHIPPED headline mean_ed_* numbers by 55-66%, and neither is covered by `assumptions_hash`, so editing either moves every emitted number under a byte-identical identity envelope. Ranking ORDER is preserved in all six legs.

**Evidence.** LITERAL 1: demoflow/src/demoflow/pipeline.py:806 `p_nonimm = read_ownership(geo, 40)` - no comment, no anchor, no constants entry; carried verbatim from the historical plan (docs/plans/2026-07-21-demoflow-tranche1.md:4695). Ownership is BANDED, so 40 selects the 25-54 band. The sibling `_band_entry_stock` docstring (pipeline.py:713-731) rejects the plan's `* 0.1` on exactly this ground: "no derivation in the spec, the plan or the constants surface, where every other model constant carries an anchor." spec:621 rules "Binds Task 25b: no uncited literals".
LITERAL 2: pipeline.py:90 `ROLL_AGE = 80`, named as a MODEL choice with its sensitivity stated and no anchor anywhere (zero hits for ROLL_AGE / "age 80" / "lumped" in the spec).
EXECUTED PROBE (/tmp/claude-1000/.../st-run-a/mutroot/demoflow/probe_pnonimm.py; committed data, central q_live, one central ED grid per leg):
  p_nonimm age 40 (25-54 band): HORS_RMR mean_ed_ref -0.00029045, MTL_RMR +0.00276776  [SHIPPED]
  p_nonimm age 55 and 60 (55-64): HORS_RMR -0.00009761 (-66%), MTL_RMR +0.00446749 (+61%)
  p_nonimm age 80 (75+): HORS_RMR -0.00041141 (+42%), MTL_RMR +0.00341586
  ROLL_AGE 75: HORS_RMR -0.00025067   |   ROLL_AGE 85: HORS_RMR -0.00012999 (-55%)
  ORDER: identical to the shipped order in every one of the six legs.
IDENTITY HALF: constants.py:282 `assumptions_hash()` hashes CENTRAL_ASSUMPTIONS + SWEEP_GRID only; neither literal is in either. Mutants M67 (age 60) and M68 (ROLL_AGE 85) change every ranking number while `assumptions_hash` and `data_vintage.source_hashes` stay byte-identical - section 9's four-field artifact identity has no code axis. In-repo this lands in test_golden.py's third attribution bucket ("the CODE moved"); for an artifact read outside the repo it is undetectable.

**Fix.** Lift both into CENTRAL_ASSUMPTIONS with CENTRAL_PROVENANCE entries - that closes the uncited-literal half and the identity half in one move, since assumptions_hash then covers them. Give the p_nonimm age a stated reason (arriving PRs skew 25-54) or make it an explicit named band selector rather than a bare age index. If they stay in pipeline.py, each needs an anchor comment of the kind every other model constant in this tree carries.

### F3 — [MED / code-defect]

**Claim.** `NULLABLE_REASONS` is a spec-closed enumeration with no exact-membership pin: two of the three non-members can be ADDED and the full 1,097-test suite still passes. A widened set reintroduces amendment #16's producer-vs-contract seam in the opposite direction - it would ship CI-green and crash the first time a real indicator value lands.

**Evidence.** demoflow/src/demoflow/output/tripwires.py:75-78. Guard-mutation, full suite per mutant on an isolated copy (baseline 1,097 passed):
  + Reason.STALE          -> 1097 passed  (SURVIVED)
  + Reason.MALFORMED_BAND -> 1097 passed  (SURVIVED)
  + Reason.FUTURE_AS_OF   -> killed by tests/test_tripwires.py::test_a_feed_dated_ahead_of_now_is_refused_not_evaluated
CONSEQUENCE, traced: with STALE nullable, `_unknown_measured` (tripwires.py:132) RETAINS current_value and as_of, and `assert_tripwire_record_valid`'s nullability branch (tripwires.py:289-294) then rejects the record its own module just built - the exact contract-vs-producer disagreement amendment #16 closed. Latent on the committed tree only because all six indicators are UNKNOWN under already-nullable reasons, so the stale/malformed branches are never reached; that is a property of today's inputs, not of the contract.
This answers the seat's named lead: NOT covered by composition. Drop-one mutation pins every MEMBER; nothing pins the SET, and the unpinned direction is widening.

**Fix.** Do not add a fourth frozenset copy. Extend `test_a_duplicate_record_from_the_producer_validates` (tests/test_tripwires.py:125) into a PROPERTY: for every Reason a producer can emit, build the record through evaluate_indicator / evaluate_pr_landings / check_registry and assert assert_tripwire_record_valid accepts it. That kills both survivors and every future widening in one test.

### F4 — [MED / code-defect]

**Claim.** THE THIRD PRODUCER/CONTRACT SEAM. A coercible-string tripwire band verdicts GREEN on the `demoflow tripwires` path (six OK, exit 0) while the emit path CRASHES on the very record the producer built - and the fail-safe sibling case (a non-finite band) correctly returns UNKNOWN/exit 1, so the two verification paths disagree and the green one is the cheap one.

**Evidence.** demoflow/src/demoflow/output/tripwires.py:106-117 `_band_endpoints` COERCES (`float(band_low)`) and returns floats, but every TripwireResult constructor re-reads the RAW spec fields: `_unknown_nullable` (126-129), `_unknown_measured` (132-135) and the OK/CROSSED terminal (163-165).
EXECUTED PROBE (isolated copy, live module):
  TripwireSpec(ind, "40000", "50000", 2026, 1, WIRED) for all six required indicators
  -> statuses ['OK','OK','OK','OK','OK','OK'];  run_exit_code(...) = 0   <- the code `demoflow tripwires` returns
  -> assert_tripwire_record_valid(tripwire_record(r)) raises: "tripwire band_low '40000' must be a number, not str"
  CONTRAST, band_low=nan: status UNKNOWN, reason MALFORMED_BAND, exit_code 1 (fail-safe)
Section 7c requires this gate to "refuse, never false-green"; the listing path false-greens. tests/test_tripwires.py:880 `test_a_numeric_field_can_never_carry_a_string` NAMES the class in its docstring but patches the record by hand (`{**rec, field: "45000"}`) instead of crossing the producer - so no test walks producer -> contract on this input.
Same grade as amendment #16: unreachable today only because pipeline.TRIPWIRE_BANDS holds float literals - a property of today's callers, not of the contract. It goes live the moment a band arrives from a config surface, which is what 7c's "bands arrive from the constants/spec surface the run declares" anticipates.

**Fix.** Rebuild the spec from the coerced endpoints before constructing any result - `spec = dataclasses.replace(spec, band_low=lo, band_high=hi)` - exactly as evaluate_pr_landings already does with `year_spec`; or make `_band_endpoints` TYPE-check rather than coerce, matching the contract validator's own "TYPE first, then finiteness" stance. Add the producer-crossing case to the property test in the NULLABLE_REASONS finding.

### F5 — [MED / code-defect]

**Claim.** The pipeline's `assert_i2_identity` call is TAUTOLOGICAL on the production path - it compares p_isq x (p_res/p_isq) against p_res - and the test that appears to pin it passes only through a monkeypatch geometry production cannot produce. This is spec section 6's own r7-F3 anti-pattern ("the identity is tautological when P_resident is DERIVED from it") instantiated one function away from where the spec names it.

**Evidence.** demoflow/src/demoflow/pipeline.py:851 `assert_i2_identity(sum(resident_t.values()), p_isq_t, surviving_t)` where `resident_t = {a: p * scale}` and `scale = p_res / p_isq` (pipeline.py:844), with `p_res = p_resident(p_isq, surviving)` (pipeline.py:840). The gate's `expected` recomputes the identical p_resident(p_isq, surviving).
EXECUTED PROBE (2,000 random frames, 101 single-year ages, 1-30 arrival cohorts): worst |lhs - expected| = 1.863e-09 against the gate's own tolerance 1e-6 + 1e-9*|expected| = 4.001e-03 at |expected| ~ 4e6 - six orders of headroom. It never raises.
WHY THE MUTATION LOOKS PINNED: deleting the call (M73) IS killed - by tests/test_pipeline.py:663 `test_the_i2_operand_binding_catches_a_mis_wired_consumer`, which monkeypatches `pipeline.p_resident` while demand/i2.py's module-local `p_resident` stays intact. That desynchronizes two references to ONE function, which the production path cannot do.
THE REAL I2 PROTECTION EXISTS AND IS PINNED, so this is a dead gate rather than an open hole: M76 (feed raw_t to native_formation) re-run WITHOUT -x -> 2 failed / 1095 passed, killed by test_golden AND by the dedicated `test_native_formation_reads_the_netted_operands_at_both_t_and_t_minus_1`; M75 (OwnerStock operand swap) killed by its own test; `assert_p_resident_nonneg` (i2.py:49) is a live gate.

**Fix.** Either compute the identity's left operand independently of `scale` (sum by_age and subtract the surviving arrivals in the pipeline, then compare against the value actually handed to native_formation), or delete the call and have demand/i2.py's docstring name the two operand tests as the enforcement. A gate that cannot fire is worse than no gate, because a reader counts it.

### F6 — [MED / code-defect]

**Claim.** The rankings row's TYPE contract has exactly one enforcement point on the emit path and that call site is deletion-survivable: removing it passes all 1,097 tests, after which `rank_stable: 1`, `rank: 0`, `rank: -3` and `mean_ed_reference: true` all ship.

**Evidence.** demoflow/src/demoflow/output/artifacts.py:491 `assert_rankings_row_valid(row)`. Mutation: delete the CALL -> 1097 passed (SURVIVED). Mutation: no-op the FUNCTION BODY -> killed by tests/test_rankings.py::test_row_allowlist_exact_and_flag_enum_reject_crash_probability. Classic body-tested / wiring-unpinned.
NOT redundant, unlike its siblings: write_json_strict's own docstring (artifacts.py:568-578) states that row-level numeric types and cross-field contracts are NOT re-run there. Measured with the call removed, on the committed rankings document:
  rank_stable=1 -> WRITTEN (walk + writer accept it)
  rank=0 -> WRITTEN
  rank=-3 -> WRITTEN
  mean_ed_reference=True -> WRITTEN
Three SIBLING call sites are also deletion-survivable but ARE redundant with the writer re-running the same walk, reported here only so the census is complete: assert_no_open_strings in rankings_document (artifacts.py:513) and in tripwire_document (artifacts.py:543), and assert_exclusion_row_valid (artifacts.py:497 - its two string positions are already bound by _VALUE_VALIDATORS and its key set by _KEY_REGISTRY). Each survived the full suite.

**Fix.** Give the row contract one owner ON the write path: either call assert_rankings_row_valid / assert_tripwire_record_valid inside write_json_strict and drop the builders' duplicates, or add an assertion in tests/test_pipeline.py that the EMITTED document's rows pass the row validators, so deleting the builder call reds.

### F7 — [LOW / code-defect]

**Claim.** `_fixed_keys`'s undeclared-node refusal is unreachable from `_walk` - dead code carrying a live-sounding claim about spec section 7's closed-schema rule.

**Evidence.** demoflow/src/demoflow/output/artifacts.py:301-306. `_fixed_keys` is called only from `_walk`'s _MAP branch when `label is None`; `_declared_kind` (artifacts.py:317-325) returns _MAP only for (), paths in _KEY_REGISTRY, or paths in _DYNAMIC_KEY_PATHS. Enumerated at runtime: ({()} | set(_KEY_REGISTRY) | set(_DYNAMIC_KEY_PATHS)) - {()} - _DYNAMIC_KEY_PATHS - _KEY_REGISTRY == [], so the KeyError branch has no reachable path. Instrumented _fixed_keys over the committed rankings.json and over a document with a map planted at an undeclared position: 0 hits on that branch; the refusal that actually fires is _refuse_kind ("declared string position $.rankings[].flags[] carries a map"). Mutation M09 (make the branch permissive) -> 1097 passed.

**Fix.** Delete the branch and let _refuse_kind own the message, or state in the docstring that it defends direct callers of _fixed_keys rather than the walk.

### F8 — [LOW / code-defect]

**Claim.** "EMISSION IS ALL-OR-NOTHING" over-claims: validation is all-or-nothing, the WRITES are a sequential loop, so an I/O failure on the second document leaves the first on disk - a mismatched-identity artifact pair that nothing in the tree cross-checks.

**Evidence.** demoflow/src/demoflow/pipeline.py:1007 heads the block; pipeline.py:1013-1021 builds both documents then writes them in `for name, document in documents.items(): write_json_strict(...)`. EXECUTED PROBE: with artifacts._dump_json raising OSError on tripwire_baseline.json only, running the identical loop over the two committed documents leaves `on disk after the failure: ['rankings.json']`. write_json_strict's own claim ("a refusal leaves NOTHING on disk") is true per FILE and false for the PAIR. No cross-file envelope check exists: refuse_cross_vintage operates within a run, over a set the pipeline itself builds.

**Fix.** Write both to *.tmp inside the loop and os.replace both after it, or narrow the heading to name the residual ("validation is all-or-nothing; the two writes are not atomic").

### F9 — [LOW / code-defect]

**Claim.** The published suppression envelope is SYMMETRIC while suppression can only ADD: measured on the committed 2025 Quebec slice the honest bound is [-709.0, +1015.0] against a published +/-887.5, so the upper end is understated by 127.5 and the interval is mis-centred.

**Evidence.** demoflow/src/demoflow/output/tripwires.py:403-405 `envelope = CELL_ROUNDING_HALFWIDTH * self.n_cells`. EXECUTED PROBE on tests/fixtures/ircc_pr_qc_slice.csv via pr_landings_realized(frame, 2025, "Quebec"): realized 60,010 over n_cells=355 (n_numeric=304, n_suppressed=51) -> published envelope +/-887.5. Honest bound, using the module's own constants: numeric cells +/-2.5 each (rounding to nearest 5; 0 of the file's cells are non-multiples), each '--' an unpublished 1-5 that contributed 0 -> [-709.0, +1015.0]. This figure rides PRLandingsEvaluation.log only - no gate reads it - so it is a reported-figure defect, not a verdict defect.

**Fix.** Publish the asymmetric interval (rounding half-width on numeric cells, one-sided [1*n_suppressed, SUPPRESSED_CELL_MAX*n_suppressed] on the markers), or subtract the suppression mass from the centre and keep a symmetric rounding term.

### F10 — [LOW / spec-gap]

**Claim.** Spec section 3 describes a pinned re-download fallback that does not exist in the tree and should not - the sentence is stale and would license a network read inside a verification path if a future implementer took it literally.

**Evidence.** spec:94 "+ sha256 pins; runtime prefers pinned re-download, falls back to committed copy on network absence - NEVER silently to a different vintage". No network path exists anywhere in demoflow/src: no requests / urllib / httpx import in any loader; pins.DATA_DIR reads committed bytes only and pipeline._verify_pinned (pipeline.py:263-281) refuses any drift. The tree's behaviour is strictly the safer subset of what the spec describes - this is the spec being wrong, not the code.

**Fix.** Strike the clause, or restate it as "committed bytes only; acquiring a new vintage is an operator act followed by a deliberate re-pin", which is what pins.py's RAW_SOURCE_SHA256 block already argues for.

## Coverage note (what was NOT checked, in the gate's own words)

RULING U'S PRESENCE-BAR INFERENCE: probed, HOLDS, and the residual measures NARROWER than the record's own published envelope - so not a finding. Measured on tests/fixtures/ircc_pr_qc_slice.csv (the only committed IRCC bytes; data/ircc_pr_by_cma.csv is deliberately absent): 560 rows, TOTAL vocabulary = {'--'} union multiples of 5, ZERO published '0' cells, minimum numeric 5, 93 '--' file-wide / 51 in QC-2025. 11 of 32 QC-2025 members carry gaps, but the INTERIOR gaps total 10 cells and every gapped member's own maximum is <=35, so the assumption's total exposure is <= ~350 landings/yr against a provincial 60,010 (0.6%) - inside the +/-887.5 the module already publishes. I could NOT test the 2015-2024 years the 31-member intersection was derived from: those bytes are not committed.

MUTATION CENSUS: 76 guard mutations (no-op body / delete subject / delete call site) each run against the FULL 1,097-test suite on an isolated copy (baseline reproduced: 1,097 passed). 65 killed, 11 survived. Four survivors are findings (NULLABLE_REASONS x2, the rankings-row call site). The other seven are explained, not left open: M06/M07/M17 redundant with write_json_strict re-running the identical walk; M09 dead code (see the _fixed_keys finding); M58 (_read_declared -> b"") equivalent - pinned files then fail _verify_pinned and the four derived artifacts fail _artifact_extracted_at's JSON parse, so only the error's ATTRIBUTION degrades (an absent file reports as pin drift); M61 (_pop_by_age absent-year raise) equivalent - the holed-lattice check eight lines down fires on all 101 ages; M65 (_projected_years contiguity) unreachable given validate.assert_statut_sublattice's exactly-one-est-to-proj-transition rule; M74 (p_isq <= 0.0) near-equivalent - assert_p_resident_nonneg fires when arrivals > 0, and the residual 0/0 raises ZeroDivisionError, which is NOT in cli.REFUSALS and would surface as a traceback rather than a named nonzero exit (worth one line in that tuple).

CONFIRMED SOUND UNDER MUTATION: all three ruling-U completeness clauses and their wirings, the degenerate-feed floor and its three branches, freshness / future-as-of / malformed-band / closed-band-endpoint semantics, check_registry's two run-level terminals, run_exit_code's coverage gate, the record source-registry binding and the nullability contract itself, refuse_cross_vintage and its two-sample wiring, ruling O's central-only reconciliation scope AND its band, the full ranking tiebreak chain, _verify_pinned, every silent-zero door pipeline.py's docstring claims (_listings_at, _arrival_flow, _split_exits, _pop_by_age's lattice, _evaluate_declared's unruled band), _arrival_year's compo YEAR_SEMANTICS shift, the ownership-join refusal and the aligned-curve consumption (M69 re-run without -x: 3 failed, killed by TWO dedicated tests beyond the golden), the derived-artifact provenance read, branch-iii exclusions, and BOTH section-6 operand bindings. Spec section 7's "no open string anywhere" claim holds structurally: _walk dispatches on the DECLARED kind, an undeclared string position raises, and the coverage claim is measured against a genuinely independent oracle traversal in tests/test_artifacts.py:197-224. The golden gate is real - test_golden.py regenerates BOTH documents through the production generate_golden -> run_pipeline path at the pinned now=2026-12 and compares parsed-then-byte with nothing normalized out.

NOT COVERED, and a next round should take these: (a) the actuarial-system boundary - cohort/basis.py's BasisError guard was not mutated and I did not run it under `python -O`, which spec section 10's basis-guard test (b) requires; (b) the loaders' internal junction and derivation logic (census / isq / compo / living_arrangement / hors_aligned) - I probed only their entry contracts and their .get(default) census, leaving the derivations to the data gate; (c) the probe notes and the section-6 -> P8 -> join-table citation coupling (amendment #14 records that as an OPEN defect with a named owner, so I left it); (d) the hde side and the import-direction pair; (e) any live-network behaviour. I did NOT run the canonical ./scripts/test-all.sh per the concurrency instruction; my baseline was the demoflow suite alone on an isolated copy. Killed mutants other than M69/M76 were run with -x, so "killed by the golden" in those rows does not exclude additional dedicated coverage.
