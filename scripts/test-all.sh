#!/usr/bin/env bash
# Canonical full-suite invocation for housing-decision-engine.
#
# WHY THIS EXISTS: the root pyproject's `testpaths = ["tests"]` EXCLUDES demoflow/tests/,
# and `demoflow/` is a SEPARATE uv project with its own env — so NEITHER `pytest` alone
# covers both suites. A repo-root `uv run python -m pytest` runs only the hde suite; a
# `cd demoflow && uv run pytest` runs only the demoflow suite. This runs BOTH and exits
# non-zero if EITHER fails. It is the canonical "did I break anything" check (see AGENTS.md).
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== hde suite (repo root) =="
( cd "$root" && uv run --extra dev python -m pytest -q )

echo "== demoflow suite =="
( cd "$root/demoflow" && uv run --extra dev pytest -q )

echo "== both suites passed =="
