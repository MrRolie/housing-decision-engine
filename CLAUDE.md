# Housing Decision Engine — CLAUDE.md

## If someone asks a housing question (the user flow)

Whoever launched Claude here wants a rent-vs-buy answer. Use the `hde` skill
(`.claude/skills/hde/SKILL.md`) for every housing question, however casual.
Its order is fixed: elicit goals → the **Missing information** gate (ask for
what the question lacks, in ONE message, before running anything; never invent
the user's own numbers) → write `scenarios/<slug>.yaml` → run → read the
assumptions and warnings back → the verdict with its decisiveness → the story.
Everything runs as `uv run hde …` from this directory; the first run installs
the engine's own dependencies (only `uv` is needed).

## Honesty contract (every answer, 2026-09-02)

Never tell the user something that is not so. Every number in an answer
carries its source class: the user's own figure, an engine anchor (cited by
name), or an estimate the assistant chose (labelled, with the direction it
biases the verdict). Missing information is said plainly ("no source for
an Ottawa property-tax rate; 1.0% of value is a placeholder") and never filled
silently; every engine warning reaches the user; a breach is never softened
into "not a breach" without naming both thresholds. A "no source for X" line
is not a failure of the answer: what the assistant had to estimate or could
not anchor is what the engine builds next.

## Surface doctrine (2026-08-26; MCP server removed 2026-09-01)

The `hde` CLI plus that skill is the only surface. Agent output: `--json`;
input contract: `--print-schema` (never describe the schema from memory);
provenance: `--print-anchors`.

## Verification (engineers — run before declaring done)

```bash
uv sync --extra dev
uv run --extra dev python -m pytest -q        # hde suite (must be green)
bash scripts/test-all.sh                      # canonical: hde + demoflow suites
```

Story plots are byte-stable: rerunning `--story` on the same config must leave
`git status` clean in `docs/story/`.

## Working reflexes (engineers)

- New feature design → design doc in `docs/specs/` before code (always)
- Multi-step implementation → plan in `docs/plans/` first, then task-by-task
- Bug / unexpected behavior → failing test reproducing it BEFORE the fix
- Config/input questions → `uv run hde --print-schema`, not memory

## Gotchas

- Real vs nominal: defaults are REAL terms; coherence warnings are judgment
  gates, not noise — surface them, don't suppress.
- `demoflow/` is a separate uv project with a path dependency that is NOT
  published (accepted teaser); hde root is standalone and must stay so.
- demoflow's `uv.lock` self-re-dirties against the sibling's live pyproject —
  do not commit that churn.
- `scenarios/` is git-ignored on purpose: users' own numbers never get committed.
