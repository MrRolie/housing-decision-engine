# Housing Decision Engine — CLAUDE.md

Claude-specific guidance. Operational rules are in `AGENTS.md`; the project skill
`.claude/skills/hde/` is the dispatch contract for housing-decision questions.

## Surface doctrine (2026-08-26)

**CLI-first.** The `hde` CLI is the registered surface; the MCP server remains
only for non-shell consumers. Agent output: `--json`; input contract:
`--print-schema` (never describe the schema from memory).

## Verification (run before declaring done)

```bash
uv sync --extra dev
uv run --extra dev python -m pytest -q        # hde suite (must be green)
bash scripts/test-all.sh                      # canonical: hde + demoflow suites
```

Story plots are byte-stable: rerunning `--story` on the same config must leave
`git status` clean in `docs/story/`.

## Working reflexes

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
