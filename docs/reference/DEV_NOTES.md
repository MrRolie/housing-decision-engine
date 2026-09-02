# Developer notes

Rewritten 2026-09-01 (the previous version described the pre-rename
`cvh_cost` package and design rationale the engine no longer follows).

## Setup and verification

```bash
uv sync --extra dev
uv run --extra dev python -m pytest -q        # hde suite
bash scripts/test-all.sh                      # canonical: hde + demoflow suites
uv run hde examples/basic_config.yaml         # CLI smoke
```

`demoflow/` is a separate uv project; the root `pytest` never runs it, and its
`uv.lock` re-dirties against the sibling `actuarial-system` — never commit that
churn (stage by explicit path).

## Typing

`pyproject.toml` carries a strict mypy config, but the tree does not pass it
(60 errors measured 2026-09-01 with `uv run --extra dev python -m mypy src`) and nothing gates it. Typing is aspirational
until the operator rules one way or the other (fix all + add a stanza to
`scripts/test-all.sh`, or drop the config). Do not present `mypy src` as a
check that passes.

## Where things live

- Engine defaults and their sources: `src/hde/anchors.py` (one registry; an
  uncited entry fails at import). The three-way pin dataclass == parser ==
  anchor is generative in `tests/test_anchors.py` — a new anchor must be wired
  to a dataclass default or declared consumed elsewhere.
- What every printed figure is and how it is computed:
  `docs/reference/ARCHITECTURE.md` § Figure glossary. The glossary is pinned
  by a test against the breakdown-key frozensets and the serializer output.
- The input contract: `src/hde/input_schema.py` (`--print-schema`), pinned by
  `tests/test_input_schema.py` (drop-one round trip over every required key).
- Agent-facing output: `src/hde/serialization.py` — the only serializer; the
  CLI `--json` renders from it (the MCP server was removed 2026-09-01).
- The verdict: `models.compute_verdict` — one computation for the story
  headline, the text report and `--json`.
- The skill: `.claude/skills/hde/SKILL.md` is the hot path (order of
  operations, intake, gates as one rule each, the answer checklist); the
  lanes, translation table, worked phrasings and rationale live in
  `.claude/skills/hde/references/`, each named in SKILL.md with when to read
  it (Claude Code's skill guidance: body under 500 lines, depth in referenced
  files). Pinned by `tests/test_skill_contract.py` over both.

## Conventions the numbers follow

Stated once, in the glossary preamble; summarised here because every new
cost component must obey them:

- Years are 1-indexed; cash flows fall at end of year and discount at
  `(1 + dr)^-t`; year-0 outlays (down payment) are undiscounted.
- Nominal mode composes inflation into every escalation:
  `(1 + g)(1 + π) − 1` (`_effective_growth_rate`), in the PV engine AND in
  the affordability numerator.
  The defaulted discount rate composes the same way (`config._discount_rate_for`);
  a typed `discount_rate` and `mortgage_rate` are used as entered. A mortgage
  in real mode prices a level real-rate payment — lower than the lender's
  nominal payment — so `coherence_warnings` flags it when an income block is
  present (round-three dogfood 2026-09-02).
- Two escalation-start conventions coexist by design: condo fees, rent and
  other recurring costs escalate before year 1 (`base × (1 + e)^t`); house
  maintenance is `rate(t) × V0 (1 + g)^(t−1)`.
- Mortgage: level ANNUAL payment at an EFFECTIVE ANNUAL rate. A Canadian posted
  rate compounds semi-annually — convert before use.
- Monte Carlo shocks are mean-one lognormal multipliers `exp(σ z − σ²/2)`
  (median `exp(−σ²/2)`; `docs/reference/CONFIG_SCHEMAS.md` § Volatility Parameters).

## Adding a cost component

1. Field on the parameter dataclass (`models.py`) — default from `ANCHORS` if
   it is judgment-bearing, plus the parser default in `config.py` and a note in
   `input_schema._NOTES` (the schema test fails otherwise).
2. Compute it in `deterministic.py` (add the breakdown key to the option's
   frozenset) and `monte_carlo.py`.
3. Add a glossary row (the completeness test fails otherwise) and, if the
   YAML can omit it, add it to `config._ASSUMPTION_KEYS` so the echo shows it.

## Style

Type hints on public APIs; no prints outside `cli.py` / `reporting.py`;
dataclasses over dicts; Google-style docstrings. Tests: one file per module,
hand-calculated oracles for PV functions, statistical properties for Monte
Carlo, and a failing test before every behaviour change.
