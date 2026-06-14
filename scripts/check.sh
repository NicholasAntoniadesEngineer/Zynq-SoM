#!/usr/bin/env bash
# check.sh — the schgen regression bar, run before every commit.
#
# Local only (no online/GitHub CI by project policy). Runs the four gates that
# must ALL pass for the board to be trustworthy:
#   1. board     every sheet gated (netlist==declared, ERC=0, visual 0-overlap)
#                + the board-level link/merge gate + cc/short detector.
#   2. selftest  gate MUTATION testing (every injected fault must be killed)
#                + cross-PYTHONHASHSEED build-DETERMINISM proof.
#   3. m1_rc     the M1 RC-spine smoke sheet (engine sanity).
#   4. pytest    unit tests (model, gates, part_gen EP synthesis, ...).
#
# Usage:  scripts/check.sh        (from anywhere; cd's to the repo root)
# Exit 0 only if every stage passes; first failure stops the run (set -e).
set -euo pipefail

cd "$(dirname "$0")/.."
PY=python3

step() { printf '\n\033[1m==== %s ====\033[0m\n' "$1"; }

step "1/4  board — all sheets + link + cc/short gate"
$PY -m schgen board

step "2/4  selftest — mutation kills + determinism"
$PY -m schgen selftest

step "3/4  m1_rc — engine smoke"
$PY -m schgen.tests.m1_rc

step "4/4  pytest — unit tests"
$PY -m pytest schgen/tests -q

printf '\n\033[1;32mREGRESSION PASS — board + selftest + m1_rc + pytest all green.\033[0m\n'
