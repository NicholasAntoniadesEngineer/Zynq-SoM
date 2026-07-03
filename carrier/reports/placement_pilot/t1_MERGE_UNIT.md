# T1 MERGE UNIT — P0..P6-core on 4a45f99 (Ring-0 review packet)

Base: **4a45f99** (T2 escape block merged). All work uncommitted in this
worktree; no stash used for the final rebase (fleet protocol — resolved via
`git checkout -m` + manual conflict resolution).

## Change inventory

Tracked (source):
- `schgen/verify/placement_flow_gate.py` — P1 single-oracle kernels
  (`flow_budget`/`bbox_gap`/`facing_dot`/`zone_centroids`/`zone_bboxes`) +
  additive `FlowTerm`/`.terms` data channel (summary text byte-identical).
- `schgen/verify/placement_contract_gate.py` — `discover_all()` +
  `wired_term_participants()` (P5b partition: exempt = near_max
  participants + templated wired sheets = {pd_input, power, usb_pd};
  guarded = {ethernet 14.0, power_som 25.0} — the rebase-caught thermal
  coupling, Ring-0 ratified).
- `schgen/verify/ratsnest_gate.py` — additive `dispersion_by_sheet`.
- `schgen/generate/pcb/placement.py` — `som_core_rect()` kernel; LEVER-L4
  per-kind exemption (P5); spec-injection threading (IM1); merged cleanly
  with T2's escape tail + GAP1.
- `schgen/generate/pcb/emit.py` — T1 composition report in generate()
  (advisory, D-5), coexisting with GAP1 copper + T2 escape emission.
- `schgen/generate/floorplan.py` — P3 pull knob (schema + invariants +
  verbatim `_anchor` geometry + exclusive packing order + export
  round-trip; `_EDGE_SEAT_BLOCKS`/`_EDGE_SEAT_ZONE_W` deleted);
  `build_plan(spec=None)` injection; out-of-repo spec-path fix.
- `schgen/__main__.py` — composition report write + `schgen compose` CLI;
  merged with T2's gate chain (T1 block precedes RETURN STITCH).
- `carrier/floorplan.json` — the ratified usb_pd exclusive pull (P3).
- `schgen/tests/test_placement_flow_gate.py` — P1 identity tests.

New (untracked):
- `schgen/generate/floorplan_compose.py` — terms/TermIndex, zone-local
  metrics (full emit rounding chain), exact evaluator (P5b guards: flow
  budgets tightened, facing abstention for guarded participants),
  measured term table + compose_report, emit-mobility model, D13 channel
  demand instrument + **T2 sidecar consumption** (`escape_corridors()` from
  carrier/escape_block.json `t1_constraints` + `corridor_intrusions`
  ledger measurement — the sidecar's named consumer), **P6-core legalizer**
  (`legalize_compact`: L1 separations w/ D13 corridors + terminus
  precedence, L2 near_max windows, L3 seed-first + Bellman-Ford V-sweeps +
  repair flips + named infeasibility, guarded weighted-median compaction,
  L5 exact accept). Constants with basis strings (GUARD_MM 4.0 measured).
- `schgen/generate/compose_repair.py` — measure_ledger (advisory floors as
  repair triggers, D-1 seat-consistency), SpecEdit catalog, banded monotone
  acceptance (7 clauses), one-step repair driver with IM5 escalation.
- Tests: `test_floorplan_compose.py` (incl. board-scale exactness w/
  same-run expectations), `test_floorplan_pull.py` (red-on-before
  archived), `test_compose_repair.py`, `test_p6_legalizer.py` (9 units),
  `test_build_twice.py` (end-to-end determinism instrument).
- Evidence: `carrier/reports/placement_pilot/t1_P0..P6*.md`, t1_ renders,
  `carrier/reports/ledger.jsonl` (GAP4; area cap 25,670 / target 24,600 —
  ratified), `t1_p3_red_on_before.txt`.
- Generated per build: `carrier/reports/floorplan_composition.txt`
  (+1 manifest line — the §3 scoping note).

## Verification bar (this base)

- ruff green; combined T1+T2 fast tests green; full-suite green on the
  28f8e15 base (510) — re-run on 4a45f99 recommended at merge.
- Board-scale suite (SCHGEN_BOARD_TESTS=1) + coexistence double build:
  results appended below (all gates incl. T2's return_stitch/escape_lanes,
  thermal PASS with the P5b partition, byte-identical builds).
- Known scalars (P5b): board 170x151 = 25,670 mm^2 (cap intact); LAW-5
  slack ~14.5%; usb_pd->power margin 10.06 mm (P6-wire's A1 target); seat
  gap 1.92 mm (<= bound-GUARD 6); motor near_max RED -48.65 (D9 pending,
  ratified, driver-gated).

## Pinned next units (fresh worktree after merge)

1. **P6-wire**: thread TermIndex/LocalMetrics/channel-demand/corridors into
   `_attempt_pack` (4 call sites; compact=True only at fixed-outline +
   final re-pack), <= +10s `--timing` proof, banded no-worsen acceptance,
   A1 verdict, renders.
2. P7 waves: ethernet (F1/F7 corridor + seat pull spec diff), hdmi_rx,
   power_som (buck template + same_side + the ratified packer
   bottom-keepout-under-THERMAL_COPPER item; graduates power_som to
   l4_exempt — re-pin the participants test).
3. P8 D9 motor move via `schgen compose --repair --allow-intent
   motor_sense:E->W` (pre-ratified; spill-as-FAIL; W-edge pre-measure).
4. P9 motor wiring wave; P10 area verdict vs the ratified cap/target.

## Coexistence gate results (4a45f99 base — FINAL)

- Board-scale suite: 34/34 PASS. Combined T1+T2 fast tests: 102 PASS. ruff
  green.
- Double `schgen board`: BOARD PASS x2, **byte-identical** (pcb ea3260e7...,
  manifest 32ca76b4..., composition report b583a8f6... — identical across
  builds). DRC 0.
- All gates green TOGETHER: LAW-5 ratsnest (cross 13,567.4/15,862);
  placement contract/flow; COMPOSITION ledger (6 hard green, motor soft RED
  archived); **T2 RETURN STITCH PASS (29/29 contacts, worst 1.777/2.0mm,
  8 stitch vias, file parity ok — T1's P5/P5b movers do NOT collide with
  the locked escape nodes)**; T2 ESCAPE LANES PASS (293 lanes, 15 GENUINE);
  THERMAL PASS (P5b partition holding on the merged tree); RETURN PATH v1
  report-only FAIL by design (SoM fact).
- Sidecar consumption live — WITH a self-caught metric correction: the
  first-cut zone-HULL overlap metric reported 22 sliver false-positives
  (hulls sweep the SoM keepout; bbox is not copper). Reworked to PART-level
  pad-copper intrusion cross-referenced against T2's own coexistence ledger
  (escape_meta.coexistence verdicts). Final measured line:
  "T2 escape corridors (D13 never-close): 6 loaded, **0 UNMANAGED part
  intrusion(s), 12 T2-coexistence-managed**" — every part inside a lane
  corridor carries a T2 STAY/CONSTRAINT verdict; nothing unjudged sits in
  the lanes. Final double build below re-proves byte-identity with the
  corrected report.

## Final artifact state (corrected report; the merge-unit hashes)

Final double build: BOARD PASS x2, byte-identical — pcb ea3260e7...
(UNCHANGED by the metric rework: copper untouched), manifest c0e5f046...,
floorplan_composition.txt dc4aa02c... (identical across builds). Corridor
line in the shipped report: "6 loaded, 0 UNMANAGED part intrusion(s), 12
T2-coexistence-managed". All gates green (RETURN STITCH 29/29 parity ok,
THERMAL 0 over-limit, DRC 0; RETURN PATH v1 report-only FAIL by design).
Ledger.jsonl: 5 entries (P0 baseline, area-cap, P5, P5b-rebased,
MERGE-UNIT@4a45f99).
