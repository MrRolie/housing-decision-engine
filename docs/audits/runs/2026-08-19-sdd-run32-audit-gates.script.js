export const meta = {
  name: "demoflow-run32-audit-gates",
  description: "Seat dispatch: the three pre-PR audit gates (QFE / stress / data-integrity), re-aimed at the SPEC",
  phases: [{ title: "Audit", detail: "three independent read-only gates in parallel" }],
}

const PREAMBLE = `
Repo: housing-decision-engine, worktree /home/mm-mike/ai_system/projects/housing-decision-engine.demoflow-t1, branch feat/demoflow-tranche1. Tranche-1 is CODE-COMPLETE and this is a pre-PR gate.

**YOU WRITE NOTHING.** This is a read-only audit. Do not edit, do not commit, do not create files in the worktree. Probe on COPIES under your own run-unique scratchpad subdir; never disable a guard in the live tree. Your return value IS the verdict — the seat writes the audit document.

**GOVERNING ARTIFACT: THE SPEC** — \`docs/specs/2026-07-21-demoflow-demographic-scenario-module-design.md\`, including amendments #7 through #16 and steering rulings A through U. **The plan (\`docs/plans/2026-07-21-demoflow-tranche1.md\`) is HISTORICAL** — read it for intent and for the test bodies it proposed, NEVER as the requirement. Since it was written the spec has taken ten amendments and rulings A–U, several of which REFUTED plan premises outright. Where plan and spec disagree, the SPEC wins; where spec and TREE disagree, that is a finding.

**CLASSIFY EVERY plan-vs-tree divergence into exactly one of:** (a) \`plan-superseded\` — the tree is right and the plan is stale, no action; (b) \`code-defect\` — the tree violates the spec; (c) \`genuine-drift\` — the tree satisfies neither, or satisfies an unwritten third thing. **Reporting a divergence flat, without this classification, is a defect in your report.** The schema carries a FOURTH value, \`spec-gap\`, which is deliberately NOT a divergence class: use it when the SPEC ITSELF is silent, ambiguous, or wrong about the thing you found. Every finding takes exactly one \`classification\`; a finding that is not a plan-vs-tree divergence at all is almost always \`code-defect\` or \`spec-gap\`.

**THE RULING LEDGER AND THE RUN RECORDS ARE INPUTS, NOT BACKGROUND.** \`docs/audits/runs/\` carries a record per seat run with its measurements, its refuted premises and its named residuals. A finding that merely restates something the ledger already rules is **derivative** — mark it \`derivative: true\` and move on. Your budget belongs to what the ledger does not cover. **Round-closure test: a round is DRY when it produces only refuted or derivative findings.**

**NAMED RESIDUALS ARE RULED, NOT OPEN.** Where a record names a residual with its assumption stated, re-raising it is derivative. What is NOT derivative: showing the stated assumption is FALSE, or that the residual is WIDER than the record claims. The live example is ruling U's presence-bar, which rests on the seat's stated INFERENCE that an unpublished IRCC month means zero landings rather than missing data — that inference is documented as an inference, and refuting it would be a real finding.

**STANDING FACTS about the current tree, so you do not mis-read them as defects:**
- All six tripwire indicators are structurally UNKNOWN and \`demoflow tripwires\` exits 1 on every vintage. One wired feed is DELIBERATELY uncommitted (committing it would flip the indicator's live state), two are wired to nothing, three are operator-supplied with no operator input. **This is the fail-safe gate working.** A fabricated operator input is the exact depth-1 defect three prior runs were spent removing.
- The committed golden (\`demoflow/artifacts/\`) therefore pins UNKNOWN / \`source_unavailable\` and a run_exit_code of 1. That is intended and documented in \`demoflow/artifacts/README.md\`.
- \`now\` is an injected input, pinned at 2026-12 for the golden, and the documents deliberately do NOT record it (the envelope is spec-closed; \`output/artifacts.py\` raises on undeclared positions). The generation path is committed source.
- Gate: \`./scripts/test-all.sh\` from the worktree root — hde 191, demoflow 1097, both suites passed. Those are the SEAT'S OWN figures on the **code tree as of \`aaf8e1f\`**; any commits after it are \`docs/audits/**\` only, so if HEAD differs when you look, check \`git log\` rather than assuming the code moved.
- **YOU ARE ONE OF THREE GATES RUNNING CONCURRENTLY IN THIS SINGLE CHECKOUT.** Do NOT run the canonical gate — the figures above are the seat's, three simultaneous suite runs in one venv is contention and roughly nine wasted minutes, and nobody is mutating the tree for it to detect. Everything you execute goes in your OWN run-unique scratchpad subdir, on COPIES.

**A SEAM CLASS THIS ARC HAS HIT TWICE — hunt it explicitly.** A PRODUCER and a CONTRACT that disagree, green because no test crosses them. Instance 1: \`artifacts.py\` validated a 64-char assumptions hash while \`assumptions_hash()\` emits 16, so the emitter would have refused the only hash any run computes. Instance 2: \`check_registry\` emitted a record its own \`assert_tripwire_record_valid\` rejected. Both are fixed. **Find the third.**
`

const SCHEMA = {
  type: "object",
  required: ["verdict", "findings", "dry", "coverage_note"],
  properties: {
    verdict: { type: "string", enum: ["PROCEED", "PROCEED-WITH-MODIFICATIONS", "REPLACE-REDESIGN"] },
    dry: { type: "boolean", description: "true if this round produced only refuted or derivative findings" },
    coverage_note: { type: "string", description: "What you did NOT get to, and what a next round should read. Absence discipline: say what you did not check." },
    findings: {
      type: "array",
      items: {
        type: "object",
        required: ["severity", "classification", "derivative", "claim", "evidence", "fix", "decision_critical"],
        properties: {
          severity: { type: "string", enum: ["CRITICAL", "HIGH", "MED", "LOW"] },
          classification: { type: "string", enum: ["code-defect", "genuine-drift", "plan-superseded", "spec-gap"] },
          derivative: { type: "boolean" },
          claim: { type: "string" },
          evidence: { type: "string", description: "file:line plus a REPRODUCED measurement or executable probe. Not an inference." },
          fix: { type: "string" },
          decision_critical: { type: "boolean", description: "true if this is a wrong-number vector for the operator's own outputs" },
        },
      },
    },
  },
}

const GATES = [
  {
    key: "quant",
    type: "mm-spine:quant-financial-engineer",
    prompt: `${PREAMBLE}

## YOUR GATE: methodology, formulas, units, arithmetic

Dimensional consistency and limiting cases on the SPEC's specifics, against the implemented code: the q_live annualization 1-(1-0.36)^(1/5); the competing-risk partition (branches sum to 1, all >= 0, including couple states); the persons->households conversions (person- vs household-denominated rates, the min-matching and excess routing); the I2 decomposition (P_resident >= 0, surviving-cohort survival arithmetic); the ED equation's units (households/households, annual); the ranking collapse determinism (ties, scenario crossings, temporal domain); the CPM basis usage (year-projection, sex mapping, 100+ absorbing bucket). Junction-type trace on every cross-source join (geography labels with their trailing-whitespace and footnote-digit reality, sex codes, age blocks under duplicate column names).

**VERIFY THE ORACLE FIXTURES by independent recomputation — a wrong oracle pins a wrong implementation.** This is the highest-value thing you can do.

**Named targets the seat is handing you:**
- **The aligned-rho operand question.** \`loaders/hors_aligned.py\` was dead code until run 30 wired it. Does consuming the aligned curve change ED's SIGN or the ranking ORDER anywhere? The rankings currently run HORS_RMR at mean ED -0.00029 through MTL_ISLAND_RA06 at +0.00721 — eight geographies, all \`rank_stable: true\`. Is that stability real or is the sweep too narrow to move it?
- **The band-entry construction** that replaced the plan's uncited \`* 0.1\` (\`pipeline.py\`, \`_band_entry_stock\`). The plan's version was booking a tenth of the gap between the rolled stock and the ISQ 75+ stock — a partial re-anchoring. Is the replacement dimensionally right, and does it conserve what it should?
- **The suppression envelope is centred where the arithmetic is not:** \`+/- 2.5 * n_cells\` treats a suppressed IRCC cell's [0,5] interval as +/-2.5 about a contributed 0, but suppression is ONE-SIDED — each \`--\` can only add. For 2025 that is 51 cells whose true contribution lies in [0, +255]. Is the stated interval honest?

The QFE debt at Task 26 was NARROWED — the direction is measured — so this is ADEQUACY review, not discovery.`,
  },
  {
    key: "stress",
    type: "mm-spine:stress-tester",
    prompt: `${PREAMBLE}

## YOUR GATE: adversarial probing of every load-bearing claim, and of the guards themselves

Probe the claims: "fail-loud, never impute"; "never a false clean" (tripwires); "the schema cannot express the forbidden quantities"; "mechanically unshippable double-count"; "every silent-zero door on the model path refuses instead".

**Spec §7 requires that EVERY string-typed position in every emitted artifact — field values, enum members, AND map keys — is registry/enum-bound or format-validated.** Determine what the code ACTUALLY enforces and where any claim exceeds it. (Do not assume the answer either way: run 30 built a real recursive walk after finding the plan's version inspected one path while claiming the general rule.)

**Guard-mutation on EVERY guard**: mutate the guard to a no-op AND delete the subject it protects AND delete the call site — a body-tested guard can still be unpinned at its wiring. Cheapest-passing-world on every done-bar, especially the golden-artifact diffs. Test-double-vs-production divergence. Degenerate ledger with cause-owner and error-direction on every loader. Composition across the shared \`assumptions_hash\`: can two artifacts mix identities?

**THE GENERAL QUESTION, and the seat wants it answered as a census, not anecdotally: WHICH SHIPPED GATES CANNOT GO RED ON ANY INPUT?** This arc has repeatedly found guards whose tests pass for the wrong reason — a test named for a vocabulary rule that was actually killed by a different clause; three tripwire bands so wide they reported OK forever; a \`refuse_cross_vintage\` called with a one-element set. All are fixed. Enumerate what remains.

**A named lead the seat is handing you:** all five members of \`tripwires.NULLABLE_REASONS\` are individually pinned by drop-one mutation, but **nothing asserts the SET itself** — no exact-membership pin exists anywhere. Is that reachable as a defect, or genuinely covered by composition?

Probe against the REAL committed workbooks, not synthetic fixtures, wherever a claim is empirical. Report each finding with a concrete executable probe.`,
  },
  {
    key: "data",
    type: "mm-spine:data-integrity-validator",
    prompt: `${PREAMBLE}

## YOUR GATE: the data layer — junctions, vintage/PIT identity, staleness

Junction-type trace on every cross-source join: geography label normalization including the trailing-space and footnote-digit reality, sex-code orientation (numeric 1/2/3, not M/F), age-block selection under duplicate column names, scenario label mapping. Year-lattice and primary-key contracts against the REAL committed workbooks — probe the actual sheets, and ask whether the pinned expectations hold on the whole population rather than one sampled row. Consumer-blast-radius per defect.

**VINTAGE / PIT IDENTITY — and the seat is giving you the state so you do not spend budget re-finding it.** The identity envelope was covering 3 of 13 committed inputs; run 30 widened it to 12, each hashed off disk through three refusal doors (absent / unhashable / pin-drifted), and \`assumptions_hash\` covers the central+sweep selection at 16 hex chars. **The non-derivative question is whether that actually closes it:** can two runs over DIFFERENT upstream bytes still emit the same artifact identity? Which of the 13 committed inputs is still outside the envelope and does it matter? Is \`extracted_at\` — per-source declared provenance read from each artifact's own \`_provenance\` block — semantically what a consumer would assume it means?

**STALENESS — silence-test the freshness gate.** Can it EVER report UNKNOWN vacuously, or stale-as-fresh? \`FEED_FRESHNESS_MONTHS = 5\` was derived from three measured Wayback vintages showing 1.5-4 months of publication lag. Is the derivation still true, and is the limit doing work?

**RULING U's completeness contract is the newest data-layer machinery and deserves your hardest look.** A plan-governed year is CLOSED only when all twelve month tokens are present province-wide, all twelve are present for each MODELED member, and every member of the code-owned \`QUEBEC_REQUIRED_CMAS\` (31, the cross-year intersection over 2015-2026) is present with at least one cell. The subset direction is deliberate. **Its named residual, with the assumption stated: non-modeled members carry a PRESENCE bar rather than 12/12, resting on the seat's INFERENCE that an unpublished month means zero landings** (the feed publishes \`--\` for 1-5 and omits true zeros). That inference is documented AS an inference and is NOT documented IRCC behaviour. **If you can refute it, that is the most valuable finding available to you in this gate.**`,
  },
]

phase('Audit')
const results = await parallel(GATES.map(g => () =>
  agent(g.prompt, { label: `gate:${g.key}`, phase: 'Audit', agentType: g.type, schema: SCHEMA })
    .then(v => ({ gate: g.key, agent_type: g.type, verdict: v }))
))

const ok = results.filter(Boolean)
log(`gates returned: ${ok.map(r => `${r.gate}=${r.verdict?.verdict}`).join(', ')}`)
return { gates: ok, missing: GATES.length - ok.length }
