# T1 P6-core — composition legalizer (engine landed, wiring pinned)

Delivered (uncommitted): `legalize_compact` + `LegalizeVar` + `_Sep` +
`channel_gap_mm` + `_bellman_ford` appended to
`schgen/generate/floorplan_compose.py`; 8 hermetic red-proven units in
`schgen/tests/test_p6_legalizer.py`.

Scope (v1, per the session's quality bar — a subtly-wrong solver in the
placement engine is worse than a scoped one):
- L0 term-free/no-DOF short-circuit (term-free projects untouched).
- L1 pairwise separations on the seed arrangement's axis (normalized-gap
  choice, ties x-then-lex) with the **Ring-0 D13 CHANNEL corridors**
  (floor 2.0 + 0.2/net, hotspot >= 6 airwires) — with the recorded
  precedence: a HARD near_max pair is a TERMINUS (D13's own nuance) and
  keeps CLEAR (the usb_pd seat, the future ethernet|rj45 MDI adjacency).
- L2 wired near_max windows: dominant-axis gap <= bound - GUARD_MM +
  perpendicular-overlap >= 0, as difference constraints (movable-movable
  and movable-fixed forms).
- L3 seed-first (a green seed is NEVER perturbed — byte-identity + timing);
  else Bellman-Ford (V sweeps, predecessor-walk-V cycle naming),
  <= REPAIR_MAX deterministic axis flips, else False -> candidate rejected
  -> outer grow (LAW 4).
- Seed-restore + L4' compaction: Gauss-Seidel weighted-median over wired
  hop pulls (W_HOP) + seed anchor (W_SEED), quantize-Q-then-CLAMP,
  MEDIAN_PASSES; compaction GUARDED (reverted wholesale if any hard term
  would go red).
- L5 exact accept through `evaluate_terms` (gate kernels, full emit
  rounding chain, GUARD + FAR_L4_GUARD incl. the P5b flow-budget
  tightening and facing-abstention for L4-guarded participants).

Red-proven units: near_max-violating seed legalized red->green through the
EXACT evaluator; contradictory windows -> named infeasibility -> False;
green seed byte-identical; D13 corridor enforced between movables (0.5mm ->
4.0mm gap); channel/terminus precedence; compaction strictly shortens a
wired hop (79mm -> 9.3mm in the unit fixture) and is guarded; determinism.

NOT YET WIRED (the pinned P6-wire unit, next session): build_plan computes
TermIndex/LocalMetrics/channel-demand once per build and threads them into
`_attempt_pack`'s four call sites; `if not legalize_compact(...): return
False` at the tail (compact=True only at the fixed-outline call + the final
re-pack); movable set = interior ∩ l4_exempt-partition participants; the
<= +10s `--timing` proof BEFORE the commit; banded no-worsen acceptance vs
the P5b baseline; A1 verdict (margin 10.06 strictly improved or the binding
window named); FLOORPLAN/renders regenerated + render verdict; ledger entry.
