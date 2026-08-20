export const meta = {
  name: "demoflow-run36-audit-gates-round2",
  description: "Pre-PR audit gates, ROUND 2 on the folded bytes (loop-until-dry) + amendment-#12 leg re-measurement + completeness critic",
  phases: [
    { title: "Audit", detail: "three gates, round 2, in parallel" },
    { title: "Completeness", detail: "what did all three miss?" },
  ],
}

const REPO = "/home/mm-mike/ai_system/projects/housing-decision-engine.demoflow-t1"

const PREAMBLE = `
Repo: housing-decision-engine, worktree ${REPO}, branch feat/demoflow-tranche1. Tranche 1 is
code-complete and this is the pre-PR gate, **ROUND 2**.

**YOU WRITE NOTHING.** Read-only audit. Do not edit, do not commit, do not create files in the
worktree. Probe on COPIES under your own run-unique scratchpad subdir. **Do NOT run the canonical
suite** — three gates run concurrently in one checkout and the figures below are the seat's own; a
suite run is ~3.5 minutes of contention and nobody is mutating the tree.

**ONE HAZARD, LEARNED THE HARD WAY LAST ROUND — read this before you copy anything.** A round-1
reviewer's \`printf >\` truncated \`demoflow/.venv/.../\_editable_impl_demoflow.pth\` IN PLACE. That file
is HARDLINKED to \`~/.cache/uv/archive-v0/…\`, i.e. **outside the worktree and shared with every other
environment built from that uv archive entry.** It was restored and verified, but the lesson binds
you: **"footprint: demoflow/** only" is a GIT-TRACKED-PATH rule, and a hardlinked venv file inside
that path reaches OUTSIDE the repo. Copying is not enough if you copy by writing THROUGH a
hardlink** — break the link first (\`rm\` then create), or copy with \`cp --remove-destination\`.

**GOVERNING ARTIFACT: THE SPEC** — \`docs/specs/2026-07-21-…-design.md\`, through amendment **#17**,
plus steering rulings A–V. **The plan is HISTORICAL**; where they disagree the SPEC wins. Classify
every plan-vs-tree divergence as \`plan-superseded\` / \`code-defect\` / \`genuine-drift\`; \`spec-gap\` is
the fourth schema value and is NOT a divergence class — use it when the SPEC ITSELF is silent,
ambiguous or wrong about what you found.

## THIS IS ROUND 2. THE DRY TEST IS THE POINT.

Round 1 (\`docs/audits/{quant,stress,data}/2026-07-21-demoflow-tranche1.md\` — **read your own gate's
file first**) returned 20 findings, 2 CRITICAL and 3 HIGH. **18 were folded; the other two were the
operator's scope call and are now BUILT.** Five substantive commits landed since:
\`98c2f10\` (the 18-finding fold + spec amendment #17), \`f5106aa\` (golden re-mint),
\`c83595e\` (the age-resolved headship curve, operator ruling V), \`16fc229\` (note discharges +
a tripwire), \`8c8e0f0\` (the final mint).

**A round is DRY when it produces only REFUTED or DERIVATIVE findings.** A finding that restates
something the ledger already rules is derivative — mark \`derivative: true\` and move on. **Your budget
belongs to what the ledger does not cover, and to the code that did not exist last round.**

**THE LEDGER IS YOUR INPUT, NOT BACKGROUND.** \`docs/audits/runs/\` carries a record per seat run with
its measurements, its refuted premises, its named residuals and its open carries — runs 33, 34 and 35
are the ones that changed the tree under you. Several of them record **the seat's own errors**; those
are recorded, not open.

## WHAT IS ALREADY CONFIRMED SOUND — do NOT re-spend on these

- **Ruling U's presence-bar inference** survived its strongest available falsification in round 1,
  probed by two gates, one against three real Wayback IRCC vintages. The residual measures NARROWER
  than the seat's record claimed.
- **All six cohort oracle fixtures** pass independent recomputation from the spec §5 branch algebra
  with exact \`fractions.Fraction\`.
- **The headship curve's per-member closure**: worst |residual| 0.000e+00 on all 15 members, BOTH
  arms, verified by the seat and by round-34's reviewer independently; two generator runs
  byte-identical; all six legacy band rates recompute BIT-IDENTICALLY.
- **The reduced-sweep fail-safe**: a reduced sweep cannot certify rank stability; mutating it away
  makes it return \`true\` off an unevaluated grid.
- **The ownership-floor tripwire fires on the run-15 failure class**: a CONSISTENT downward extension
  (both the band spec and the floor constant moved together) reds it while both twin pins stay green.

## THE SEAM CLASS — THREE FOUND AND ALL THREE FIXED. IS THERE A FOURTH?

A PRODUCER and a CONTRACT that disagree, green because no test crosses them. (1) \`artifacts.py\`
validated a 64-char assumptions hash while the producer emits 16. (2) \`check_registry\` emitted a
record its own validator rejected. (3) \`evaluate_indicator\` emitted a \`malformed_band\` record
carrying a non-finite endpoint its own validator rejects. All fixed, and a generalized property now
asserts that every record a producer can emit validates against its contract validator. **Round 1
was told to find the third and did. Find the fourth, or establish that the generalized property
closes the class.**

## THE SURFACES THAT DID NOT EXIST LAST ROUND — this is where your budget should go

- **The age-resolved headship curve** (\`census.py\`, \`scripts/gen_headship.py\`,
  \`data/headship_by_age.json\`): two arms, 101 single-year rates, exposure-abscissa monotone
  cumulative Hermite, a range certificate, a per-member closure block, and a rewritten
  \`_zero_support_note\`.
- **The full robustness sweep** (\`pipeline._sweep_legs\`, \`_rank_stability\`): every declared axis at
  both endpoints plus the join-table ratio override, ten-plus legs, verdict by UNION, and a
  configurable leg count whose committed default is the FULL set.
- **The identity envelope at 13 sources**, including the CPM mortality basis digested through a
  public surface, and \`assumptions_hash\` now spanning CENTRAL_ASSUMPTIONS + SWEEP_GRID +
  MODEL_CHOICES + the immigrant-inputs join-table selection.
- **The committed golden**: \`assumptions_hash\` \`9a876ab547fcafdd\`, every mean ED positive,
  \`rank_stable\` false on all eight rows, \`exclusions\` empty.

**Gate at dispatch, the seat's own run:** hde **191** / demoflow **1167** / both suites passed, code
tree as of \`6784c03\`. Commits after it are \`docs/audits/**\` only — check \`git log\` rather than
assuming the code moved.
`

const SCHEMA = {
  type: "object",
  required: ["verdict", "findings", "dry", "coverage_note"],
  properties: {
    verdict: { type: "string", enum: ["PROCEED", "PROCEED-WITH-MODIFICATIONS", "REPLACE-REDESIGN"] },
    dry: { type: "boolean", description: "true iff this round produced ONLY refuted or derivative findings" },
    coverage_note: { type: "string", description: "What you did NOT check, and what a round 3 should read. Absence discipline: state what went unexamined." },
    remeasurement: { type: "string", description: "QUANT GATE ONLY: the amendment-#12 leg re-measurement deliverable. Other gates omit." },
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
          decision_critical: { type: "boolean" },
        },
      },
    },
  },
}

const GATES = [
  { key: "quant", type: "mm-spine:quant-financial-engineer", prompt: `${PREAMBLE}

## YOUR GATE: methodology, formulas, units, arithmetic — round 2

Round 1 raised five findings; the CRITICAL (a one-of-five-axis \`rank_stable\` attestation) and the
HIGH (the banded-curve artifact) are both BUILT OUT now. **Re-audit the constructions that replaced
them.**

Priority order:
1. **The curve's mathematics.** Closure is confirmed sound — do not re-spend there. Audit what closure
   does NOT constrain: the WITHIN-MEMBER shape. Each published member pins one linear functional and
   leaves 4, 9 or 15 degrees of freedom. Is the monotone-Hermite-on-cumulative-persons construction
   dimensionally coherent? Is the range certificate a real bound or an assertion? **The open-ended
   85+ member is pure assumption on ~209,463 persons whose exposure GROWS — 85+ rises from 28.19% of
   75+ in 2021 to 41.78% by 2051 — and no sweep axis prices it. Is that exposure acceptable, and can
   you bound its effect on ED?**
2. **The osculatory overshoot at 74/75**: peak 0.66202 at age 77, +2.2% over the member-rate hull,
   where the member width changes 5→10 AND the rate reverses. Round 1's judge did NOT measure its
   isolated contribution to the ranked quantity. Measure it.
3. **The sweep's arithmetic.** Ten-plus legs, one axis off-central per leg, verdict by UNION. Is a
   union over one-axis-at-a-time legs the right answer to spec §7b's question, or does it MISS joint
   perturbations that would reorder? The code argues a joint leg could not attribute a reorder —
   audit that argument.
4. **THE NAMED DELIVERABLE — return it in the \`remeasurement\` field.** Spec §7 amendment #12's QFE
   legs (0.195–0.337% / 0.96–1.65% / 30×–200× / equality at |ED| ≈ 19–21%/yr) were measured against
   the RETIRED banded curve and the tree now advertises them as STALE. **Re-measure them on the
   landed curve.** Round 34 measured one input already: the sub-25 gross positive gain the ownership
   floor discards moves from 23.0–25.9k to 17.6–20.5k (−23%) and its character inverts from a
   coarsening artifact to genuine formation mass. Give the seat numbers it can land.
5. **The 2026–2029 negative D_native window** (−25.1%/−19.7%/−15.5%/−13.2%) straddles the \`p\`→\`proj\`
   vintage seam. Round 1 could not separate cohort geometry from junction geometry. Separate them.
6. **A figure the seat reported is UNRECONCILED and it is arithmetic:** 26.1% (in \`formation.py\`'s
   comment) vs 26.72% (in the run-34 record and the seat's report to the operator) for MTL_RMR fc
   concentration. Likely a pooling convention. **Settle it.**` },

  { key: "stress", type: "mm-spine:stress-tester", prompt: `${PREAMBLE}

## YOUR GATE: adversarial probing, and the guards themselves — round 2

Round 1 raised ten findings including the CRITICAL. **The fixes added a lot of new guard surface, and
new guards are exactly where your value is.**

Priority order:
1. **GUARD-MUTATION ON EVERYTHING THAT LANDED SINCE ROUND 1** — the curve's gate set (per-member
   closure, range certificate, support, zero floor, tail non-monotonicity), the sweep's fail-safe and
   its configurable leg count, the 13-source envelope's three refusal doors, the ownership-floor
   tripwire, and the generalized producer/contract property. For each: mutate the guard to a no-op,
   AND delete the subject it protects, AND delete the call site. **A body-tested guard can still be
   unpinned at its wiring.**
2. **THE CENSUS QUESTION, and the seat wants it as a census rather than anecdotes: WHICH SHIPPED
   GATES CANNOT GO RED ON ANY INPUT?** Round 1 found three vacuous tripwire bands, a
   \`refuse_cross_vintage\` called with a one-element set, and a test named for a vocabulary rule that
   a different clause was actually killing. All fixed. **Enumerate what remains.**
3. **Three carries the ledger records as UNPINNED — confirm or refute each, and say which:**
   (a) nothing mechanically pins \`formation.py\`'s corrected acceptance-metric prose, and round 1
   caught a FALSE claim in that exact block; (b) the ownership-floor tripwire's
   \`pytest.raises(match=…)\` catches "ownership lattice floor MOVED" but NOT the amendment-#12
   obligation text the note advertises it as carrying; (c) the internal layering gate is
   ONE-DIRECTIONAL — nothing scans loaders for model-tree imports, and \`constants.assumptions_hash\`
   now imports \`demand.immigrant_inputs\` call-locally to dodge a cycle.
4. **A COUPLING WORTH ATTACKING:** artifact provenance notes ride the artifact DIGEST by deliberate
   design, so a note now names a TEST — meaning a pure test RENAME changes \`headship_by_age.json\`'s
   bytes, hence \`data_vintage\`, hence both goldens, and it fails as "the DATA moved" when no data
   moved. Deliberate consequence or latent defect? **Argue it with a probe.**
5. **\`_zero_support_note\`'s bound renders with \`{:.1e}\` and then asserts the rate is "below" it.**
   Round-half-even means a future vintage could round DOWN and make "below" false. True today
   (2.5653e-5 < 2.6e-5). Is it reachable?
6. **The second declaration the ledger names:** \`pipeline\`'s \`range(25, 101)\` against
   \`formation.OWNERSHIP_LATTICE_FLOOR = 25\` — the exact redeclaration class a new guard forbids for
   two other choices, and that guard is literal-exact so a whitespace variant slips past it.` },

  { key: "data", type: "mm-spine:data-integrity-validator", prompt: `${PREAMBLE}

## YOUR GATE: the data layer — junctions, vintage/PIT identity, staleness — round 2

Round 1 raised five findings; its HIGH (the CPM mortality basis outside artifact identity) is FIXED
and the envelope is now 13 sources. **Audit whether that actually closes it, and audit the new data
surface the curve created.**

Priority order:
1. **DOES THE 13-SOURCE ENVELOPE CLOSE THE QUESTION?** Round 1 asked "can two runs over different
   upstream bytes emit the same artifact identity?" and the answer was YES. **Is it still yes?**
   Enumerate every input the run READS and every input the envelope HASHES, and diff those two sets.
   The mortality basis is digested through a public surface rather than a file path — audit whether
   that digest actually discriminates the thing it claims to (round 1's fold measured that BOTH the
   base tables and the improvement scale move it; verify independently).
2. **THE CURVE IS A NEW DERIVED-ARTIFACT JUNCTION.** \`headship_by_age.json\` is generated from a
   census extract (round-to-5 household counts) DIVIDED BY an ISQ single-year population (no
   rounding) — two sources with different rounding regimes, joined per age. Audit the junction:
   member-span-to-age mapping, the 75-84 TEN-year member, the open-ended 85+ closing only because
   the denominator terminates at 100+, and the \`_provenance.rounding_note\`'s claim that no correction
   is applied to either side.
3. **STALENESS, re-audited.** \`FEED_FRESHNESS_MONTHS = 5\` was derived in END-OF-PERIOD FRACTIONAL
   months and consumed in INTEGER month-index differences — round 1 found that and it is in the
   ledger. Confirm the fold fixed it rather than restating it.
4. **\`extracted_at\` carries TWO semantics under one field name** across the 13 entries (round 1's
   MED): the date bytes were pulled for ACQUIRED sources, versus something else for DERIVED ones.
   The curve added another derived entry. Is the field still honest?
5. **PIT: the curve is PIT-FIXED at base year 2021 and multiplies PROJECTED populations to 2051.**
   Audit that: a 2021 headship schedule applied to a 2051 age structure is a stated modelling
   choice, but is it stated where a consumer meets it, and does anything silently imply it is
   time-varying?
6. **The \`p\`→\`proj\` vintage seam at 2026** — the first projected year — now carries a measured
   D_native anomaly. Is the seam handled correctly at the loader level, or does the anomaly indicate
   a junction defect?` },
]

phase('Audit')
const results = await parallel(GATES.map(g => () =>
  agent(g.prompt, { label: `gate2:${g.key}`, phase: 'Audit', agentType: g.type, schema: SCHEMA })
    .then(v => ({ gate: g.key, agent_type: g.type, verdict: v }))
))

const ok = results.filter(Boolean)
log(`round-2 gates: ${ok.map(r => `${r.gate}=${r.verdict?.verdict}/dry=${r.verdict?.dry}`).join(', ')}`)

phase('Completeness')
const critic = await agent(`${PREAMBLE}

## YOU ARE THE COMPLETENESS CRITIC. You are not a fourth gate and you must not re-audit.

Three round-2 gates just returned. Your single question: **WHAT DID ALL THREE MISS?**

${JSON.stringify(ok, null, 1)}

Read their \`coverage_note\` fields first — each states what it did NOT check. Then answer:

1. **Which modality was never run?** The gates read code, probe with scripts, and re-derive
   arithmetic. What KIND of examination did none of them perform on this tree?
2. **Which load-bearing CLAIM in the tree is still unverified by anyone**, across both rounds? The
   spec, the artifact provenance notes and the module docstrings all make assertions; the ledger
   records which have been checked. Name one nobody has tested.
3. **Which SURFACE went unread?** Enumerate what exists under \`demoflow/src\`, \`demoflow/data\`,
   \`demoflow/scripts\` and \`demoflow/artifacts\` and identify what neither round touched.
4. **Is the round DRY?** Three gates each returned a \`dry\` verdict for itself. Judge the ROUND: does
   the union of what they found consist only of refuted and derivative findings, or is there
   genuinely new signal? **Say so plainly — the seat is deciding whether to stop looping.**
5. **What would a round 3 read that a round 2 could not?** If the honest answer is "nothing worth the
   tokens", say that. **A recommendation to STOP is a valid and valuable output** — this arc's
   default pressure is DELETE, and an audit loop that cannot terminate is its own defect.

Do not repeat their findings back. Your value is in the gaps.`,
  { label: 'completeness-critic', phase: 'Completeness' })

return { round: 2, gates: ok, missing: GATES.length - ok.length, completeness: critic }
