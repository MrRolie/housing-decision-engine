# Demographic Housing-Flow Model — Grounding Dossier (2026-07-21)

Research pack behind the "boomer sell/transfer wave vs immigrant buy demand → crash likelihood?" question
(2026-07-21, 6 parallel research agents). Doc-only artifact; seed material for a future spec if the
build is greenlit.

## Verdict (adjudicated in-session)

**BUILD-REDUCED.** The crash-probability-over-decades form is unbuildable (Mankiw–Weil-class failure
mechanisms all apply at full force in Québec; CHSP structurally excludes Québec so the one defensible
method — cohort ownership-retention tracking — is data-blocked; immigration is a reflexive policy
variable, not a forecastable demographic; demographics produce slow periphery grind, not crash-shaped
tail events). The buildable form is a **policy-indexed conditional scenario + tripwire module** feeding
housing-decision-engine's S4b market-scenario layer (which currently has no principled way to set shock
parameters). Forbidden output: any unconditional P(crash) or point price forecast.

Altitude ruling: skeptic's guard wins over the designer's full multiple-decrement proposal for v0/v1 —
deterministic cohort roll-forward with sensitivity bands; NO new decrement machinery in actuarial-system
yet (import CPM2014/CPM-B tables + get_qx only). The designer's calibration discipline survives at any
altitude: mortality counted exactly once (Fork A: ISQ population-by-age, own headship/ownership/decrements);
CMHC 36%/5yr (75+, QC) is survivor-conditional excluding death → annualize (~8.5%/yr) and never mix with
Myers all-cause retention (0.26–0.31/decade, sanity check only); exits modeled at household level
(last-survivor approximation), not individual deaths.

## Files

- `demo_literature.md` — Mankiw–Weil autopsy, Myers/Fannie Mae cohort-retention method, Japan bifurcation,
  Canadian/Québec evidence (senior sale rates FALLING 38.6%→36%; QC natural decrease realized 2025).
- `demo_data_landscape.md` — full free-data inventory (ISQ projections 3 variants to 2071 at RMR/MRC,
  Census tenure×age, IRCC PR-by-CMA, MIFI plans, CMHC HMIP, rôle d'évaluation, Registre foncier transfer
  stats). Decisive gap: CHSP excludes Québec — no owner-level age×immigration linkage exists for QC.
- `demo_actuarial_system.md` — repo audit: CPM2014/CPM-B + Lee-Carter/CBD present and runnable (76 tests);
  zero multi-state/decrement machinery; scalar single-life API; module-global mortality basis (v1
  concurrency assumption).
- Prior-art check (no separate file): an earlier internal demographic model was reviewed for overlap and
  found disjoint — it projects equity-market behaviour, not housing supply/demand, and shares no code.
  Its age-cohort-projection-with-sensitivity-bands *method* is transplantable as a starting shape; nothing
  is reusable by import.
- `demo_design.md` — full model design (flow identity, decrements, estate-lag convolution, immigrant
  YSL tenure curves, plex owner-occupier-landlord channel, S4b ScenarioPrior output contract, walking
  skeleton). Load-bearing skeleton boundary = actuarial-system get_qx firing live with QC CPM2014 basis.
- `demo_skeptic.md` — the epistemic attack: policy endogeneity/reflexivity, timescale category error,
  decision-relevance test (~zero on buy/don't-buy vs the 30%-drawdown-survival test; modest on borough
  selection; negative if used to relax stress for core Montréal).
