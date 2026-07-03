# T1 P4 — repair driver (`schgen compose`) — evidence

Delivered (uncommitted, for Ring-0 review):

- `schgen/generate/compose_repair.py` driver half:
  - `SpecEdit` catalog: `AddPull` (ladder 2/5/10/20/40/60 — judgment:
    doubling ladder bounded by the D11-proven 60.0 seat weight; refuses a
    second pull per block), `SetPullWeight` (ladder above current),
    `MoveEdgeBlock` (INTENT — reachable only via `--allow-intent
    NAME:FROM->TO`), `CompositeEdit` (atomic move+pull, IM8; intent iff a
    member is). Every candidate carries its `target_key` term.
  - `plan_replica_metrics` / `evaluate_candidate`: the REAL `build_plan` +
    zone packer with the candidate spec INJECTED (IM1 threading landed at
    P3) — ORDER ONLY (IM9: mobile-sheet mm-scale error documented); the
    emitted board is the arbiter. Contractually SINGLE-THREADED
    (fp.BOARD_W/H globals — the 2026-06-19 race class; comment in code).
  - Candidate pre-filters: predicted plan spill = REJECT; predicted hard
    RED = REJECT. Ranking: fewest predicted soft-reds, then aggregate hard
    margin, then area; deterministic describe() tiebreak.
  - `banded_accept(before, after, target_keys, allow_area_growth)` — §5 law
    3 verbatim: gates PASS / A'<=A (area growth allowed ONLY as the IM5
    intent escalation, which REPORTS and still declines auto-accept) /
    target GREEN-or-improved / no term leaves GREEN / FRAGILE (below-floor)
    never lose margin / non-target RED never lose margin (IM3) / per-sheet
    contract-violation counts no-worsen.
  - `repair()`: ONE applied step per invocation; apply -> full `schgen
    board` subprocess -> re-measure -> banded accept -> REVERT the JSON on
    any rejection. Ledger (compose_ledger.json/.md) written by the driver
    only.
  - `propose()`: edge-block subjects are INTENT-GATED (never proposed
    unratified; printed as "INTENT-GATED ... --allow-intent"), interior
    near-anchored subjects at an edge-listed target get the SEAT ladder
    (exclusive+inboard — the ethernet-wave reviewed diff), spec-unpinned
    subjects are reported for a reviewed pinning first.
- `schgen compose` CLI: `--measure | --repair [--dry-run]
  [--allow-intent NAME:FROM->TO]...` (subparser beside floorplan).
- `schgen/tests/test_compose_repair.py`: 16 hermetic tests — every
  acceptance clause has a violating pair REJECTED with a named reason
  (gate-fail, area growth + the IM5 escalation path, GREEN->RED, FRAGILE
  margin loss, non-target RED deepening + target-must-improve, contract
  count worsening); SpecEdit semantics (second-pull refusal, move
  validation, composite intent); propose determinism; unratified-intent
  impossibility; seat-ladder shape; ladder-above-current; allow-intent
  parse. Board-scale dry-run (env-gated): the carrier's only trigger today
  is the motor advisory RED whose subject is an edge block -> dry-run
  proposes ZERO unratified edits and reports D9 as intent-gated (spec P4
  acceptance).

Board-untouched phase: no default-path behavior change (spec threading is
default-None; proven by the P2/P3 byte-identity gate which ran WITH this
code).
