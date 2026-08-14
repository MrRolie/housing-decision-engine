
---

## OUTCOME — SEAT_QUESTION halt, 2026-08-14 (exemplary; superseded by run 17)

The probe **built nothing and halted correctly.** Mid-sweep it found a cube that contradicted a
spec premise ruled the day before, and rather than write a gated artifact on a premise under
revision — or omit the implication next to a correctly-cited number, which is the depth-3 defect its
own mandate names — it reported and stopped. Tree byte-clean at the halt, `git status` empty.

**What it found:** StatCan **43-10-0060-01** (CURRENT, 2021 Census) crosses `Immigrant and
generation status` with `Population living in a dwelling owned by some members of the household` at
BOTH modeled CMAs, Québec included — refuting amendment #7's "no CMA-level measurement exists".
P4's "0 of 80 immigrant cubes carry tenure" was true AS SCOPED (98\* family, title tier); the cube is
a 43\* whose title carries a housing term and no immigrant or tenure token, so it fell outside both
tiers. Second time in this arc an absence claim proved to be a property of the search rather than of
the data (ruling F was the first).

**Seat re-verification, independent and live** (the same discipline rulings F and I got before their
amendments): all 12 reported values reproduced byte-exact against the WDS coordinates, coordinate-
keyed not zipped. The seat then measured the two members the halt had NOT — `Admitted more than 10
years ago` (the settled analogue of ruling P's own affirmed reasoning) and `Non-permanent
residents` — which is what turned the disposition:

| geography | non-imm | all imm | recent <10y | **settled >10y** | NPR |
|---|---|---|---|---|---|
| MTL CMA | 66.1 | 55.8 (0.8442) | 37.9 (0.5734) | **64.0 (0.9682)** | 13.6 (0.2057) |
| QC CMA | 69.5 | 51.1 (0.7353) | 36.9 (0.5309) | **64.1 (0.9223)** | 11.8 (0.1698) |
| QC prov | 70.4 | 56.3 (0.7997) | 38.5 (0.5469) | **64.9 (0.9219)** | 14.0 (0.1989) |

The apparent contradiction sized correctly: the out-of-band 0.7353 belongs to the ALL-IMMIGRANT
member, a stock diluted by recents that ruling P's reasoning had already set aside. On the settled
member both CMA values sit INSIDE the pinned band and near the 0.911 pin — **ruling P's selection
was corroborated; only its sourcing premise fell.**

**Headship:** heading to ABSENT and now ruled so. The sweep (8,206 cubes → 994 title-selected →
metadata on all 994) found 156 immigrant-dimension cubes and 16 household-maintainer cubes with an
EMPTY intersection, and no household-SIZE dimension crossed with immigrant status either.

**OPERATOR RULED BOTH (2026-08-14) → RULINGS Q and R, spec amendment #8, committed `1f6eacb`:**
Q re-points the ratio to 43-10-0060 per geography on the settled member (three transport axes → one,
and the r5-F4 direct tier goes live again, superseding #7's empty-tier clause); R transports the
model's own general headship curve, `borrowed_prior` on immigrant status, seat-computed at MTL_RMR
0.4332 / QC_RMR 0.4394 / HORS_RMR 0.4529 with a free floor gate (headship must exceed the immigrant
living-alone share, 0.134 / 0.127).

- outcome: **HALTED (SEAT_QUESTION), no fix rounds, nothing built** — the correct outcome. Superseded
  by run 17 (`2026-08-14-sdd-run17-p8-successor.md`), which builds the probe on the settled ground.
  A fix/halt has no resume: fresh successor dispatch.
- `ADVISOR RULING FIRED @p8-halt-disposition` — cost: transcript-scale proxy, full forward at ~330k.
  Catches adopted: size the contradiction by member (the out-of-band figure belongs to the member
  ruling P already rejected); present the settled-vs-all-immigrant member choice to the operator
  rather than deciding it; name the METRIC axis UNSIGNED (its direction turns on within-group
  household-size differentials and is unmeasured — writing a direction would be the depth-2 class in
  the seat's own voice); and the headship fallback the seat had not named — transport the tree's own
  curve, which is what made 25b buildable instead of blocked.
- `ADVISOR RATIFY FIRED @amendment-8` — logged in run 17's record.

## Carry (mechanism, seat-authored — supersedes this record's earlier carry #3)

The re-point makes carry #3 above **STALE: do not execute it as written.** Per-geography centrals
cannot live in the scalar `CENTRAL_ASSUMPTIONS["immigrant_ratio_center"]`. Pre-ruled mechanism for
25b: DELETE that key from `CENTRAL_ASSUMPTIONS` and `SWEEP_GRID` in ONE edit (the keyset-equality
test binds them, so a half-edit reds); per-geography ratios live in the join table as cited Anchors;
Task 29's sweep perturbs the ratio through a uniform join-table override spanning [0.155, 1.033],
with the span still sourced from `CONSTANTS["immigrant_ownership_ratio_sweep_span"]` — which keeps
the T29 "sweep ALL banded axes" carry satisfiable and keeps P4's anchors load-bearing rather than
cullable.
