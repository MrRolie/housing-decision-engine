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

# ---------------------------------------------------------------------------
# Running from a git WORKTREE
# ---------------------------------------------------------------------------
# demoflow depends on a sibling package by RELATIVE path (`../../actuarial-system`,
# an operator ruling — see demoflow/pyproject.toml). From a worktree that resolves
# to <repo>/.claude/worktrees/actuarial-system, which does not exist, and `uv`
# refuses before running a single test.
#
# This gate must never report success on one suite while silently skipping the
# other, so it resolves the sibling or REFUSES. The link it creates lives inside
# this repo's own gitignored worktree directory, is idempotent, and is announced.
# The sibling sits beside the MAIN checkout, which is not `$root/..` from a
# worktree. `git rev-parse --git-common-dir` points at the main checkout's .git
# whatever tree we are standing in, so its grandparent is the directory the
# sibling shares with this repo.
main_git="$(cd "$root" && git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
if [ -n "$main_git" ]; then
  sibling="$(cd "$(dirname "$main_git")/.." && pwd)/actuarial-system"
else
  sibling="$(cd "$root/.." && pwd)/actuarial-system"
fi
expected="$(cd "$root/demoflow" 2>/dev/null && pwd)/../../actuarial-system"
if [ ! -e "$expected" ]; then
  if [ -d "$sibling" ]; then
    link_dir="$(dirname "$expected")"
    mkdir -p "$link_dir"
    ln -sfn "$sibling" "$expected"
    echo "== note: linked $expected -> $sibling"
    echo "   (running from a worktree; demoflow's relative path dependency needs it)"
  else
    echo "REFUSING: demoflow's path dependency does not resolve." >&2
    echo "  expected: $expected" >&2
    echo "  and no sibling package at: $sibling" >&2
    echo "  Running only the hde suite here would report a green gate for half the" >&2
    echo "  tests, so this exits instead. Run from the main checkout, or place the" >&2
    echo "  actuarial-system package beside this repo." >&2
    exit 2
  fi
fi

echo "== hde suite (repo root) =="
( cd "$root" && uv run --extra dev python -m pytest -q )

echo "== demoflow suite =="
( cd "$root/demoflow" && uv run --extra dev pytest -q )

echo "== both suites passed =="
