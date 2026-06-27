#!/usr/bin/env bash
# scripts/check.sh — the local regression bar (no online CI by project policy).
#
# Stages, stopping at the first failure:
#   0. ruff   — lint gate (schgen/), BLOCKING. Green on the current tree by
#              construction (config: pyproject.toml [tool.ruff]); fails the
#              moment new code trips a still-enabled rule.
#   1-4.      — board + selftest + m1_rc + pytest, via `python -m schgen check`
#              (the canonical four-gate bar; see schgen/__main__.py:cmd_check).
#
# Run from the repo root:  scripts/check.sh
#
# Determinism: PYTHONHASHSEED=0 matches how the gates assert byte-stable output.
set -euo pipefail

# Resolve repo root from this script's location (works regardless of cwd).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

export PYTHONHASHSEED=0
export PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
red()  { printf '\033[1;31m%s\033[0m\n' "$1"; }
green(){ printf '\033[1;32m%s\033[0m\n' "$1"; }

# ---- Stage 0: lint (BLOCKING) --------------------------------------------
bold "==== 0/5  ruff — lint gate (schgen/) ===="
if ! command -v ruff >/dev/null 2>&1; then
    red "REGRESSION FAIL: ruff not installed (pip install ruff — see requirements.txt)."
    exit 1
fi
if ! ruff check schgen/; then
    red "REGRESSION FAIL at: 0/5 ruff lint gate"
    exit 1
fi

# ---- Stages 1-4: the schgen four-gate bar --------------------------------
bold "==== 1-5  schgen check — board + selftest + m1_rc + pytest ===="
if ! python3 -m schgen check; then
    red "REGRESSION FAIL in schgen check (board/selftest/m1_rc/pytest)"
    exit 1
fi

green "REGRESSION PASS — ruff + board + selftest + m1_rc + pytest all green."
