# PLATFORM REWORK — overnight campaign tracker (branch: platform-rework)

*Live per-unit status. Resume here. Mandate: docs/AI_PLATFORM_ROADMAP.md to the final
product; NO master merge until user approval. Baselines: carrier pcb md5 e405097b
(188x165, deterministic, all gates green); schematic goldens locked (user: golden).*

## Units
| # | Unit | Status |
|---|---|---|
| U1a | Project spec v1 (carrier/project.json + loader) + extract _WIRED_SHEETS | DONE |
| U1b | Extract _PILOT_PROX_SHEETS + SOM pose defaults to spec | DONE |
| U1c | Declarative module-face anchors (kill b.name=="power_som") + reg-band prefixes | DONE |
| U1d | Byte-identity proof through the spec path (md5 e405097b) | DONE |
| U1e | ModuleGeom: module pcb/interface paths from spec (generalize SomGeom entry) | DONE via PROJECT_ROOT indirection (29 modules) |
| U1f | --project CLI + CARRIER path resolution via project root | DONE (env pre-parse, loud fail, identity 2f13efe8) |
| U1g | devkit_mini second-project proof: green board, ZERO engine edits | NEXT-STEP #1 (authoring campaign; recipe in RETROSPECTIVE) |
| U2a | Defect-injection corpus library + gate-fires proof per class | DONE (13 tests, 1.1s) |
| U2b | Fast flow/facing synthetic harness (validated vs corpus + visual sample) | pending |
| U3a | Wire contracts: coverage 19 -> 0; cascade fixes mechanized | DONE: 23/23 wired, EXIT 0 all gates, 215x168, deterministic 2f13efe8 |
| U4a | board_verdicts.json always-on structured verdicts | DONE (verified written) |
| FIN | Deep retrospective vs all user asks + decided next steps | DONE: docs/PLATFORM_REWORK_RETROSPECTIVE.md |

## Log
(newest first)
- SECOND-TIER SCAN AUDIT (evening): zero sites qualified — silk 1.78s, ratsnest Prim 0.023s, fanout 0.02s, refdes 0.005s, all under the 2s bar, skipped with numbers (empty diff by finding; prototypes preserved in scratchpad). Real residual heat named: (a) ratsnest net_pad_positions x41 recompute ~7.6s/build — fix is a HOIST i.e. a cache, blocked on the no-memoization law, AWAITS USER AUTHORIZATION; (b) stage_templates seat-solver backtracking ~60s/124.8M overlaps — byte-pinned by search order, a campaign of its own.
- SPATIAL HASH LANDED (evening, redo-proven): the earlier "identity failure" root cause was NOT a code leak — carrier/escape_block.json is a build OUTPUT read back as INPUT, and the compared builds straddled sidecar generations (the torn pair is visible inside 70d4139 itself: FLOORPLAN.md 214x167 beside a 215x167 PCB). With sidecar states pinned: pristine==hash byte-for-byte on BOTH states, zero trace divergence, 2.11x pcb-phase / 1.86x full build (orchestrator-measured 328s), 84 worker tests + 7 landed tests green. Sidecar-loop explicitness chipped (task_813fb8b9). Supersedes the earlier "semantic leak suspected" note.
- RECORD CORRECTION (2026-07-28 evening): commit 70d4139's message overclaims — the spatial-hash kernel was NOT in that commit (a silently-failed apply, caught post-push). 70d4139 actually landed: edges-as-membership + edge_order pinning with MEASURED orders (S tx-first + W lcd-first, user-driven, cross-airwire 17494.7->17243.0), coverage lint (231/0/88 baseline), artifacts. The hash REDO is tracked separately: on this tree the worker's hunks produced a trace-divergence-free build whose BOARD still changed (md5 46b2eecf->65fc1702, 17243->17496.5) = a semantic leak outside the traced kernel (far_ceil/max_reach threading x legalizer-fix interaction suspected); identity gate failed -> not landed. Pipeline hardening adopted: every apply verified by signature-grep before anything downstream.
- VISUAL AUDIT CAMPAIGN (2026-07-28, user-driven): all 23 contract subsections inspected (3D crops + per-sheet ratsnest + MST distance tables). 3 rounds landed: 25+ new structures across 12 sheets (motor in-line chain, lcd boost train 37.5->5.2mm, usb_jtag crystal loop 14->3mm, pd_input analog straps, hdmi_tx flow-through, pmod banks, uart_bridge seat 125->43mm, camera/usbc/microsd/fmc/pmodx). Engine: structure-derived member side-override; floorplan overlap REJECTION (legalizer accepted overlapping rects — deep fix chipped); seam quantization guard; seat-kernel pad faces; snap-erosion allowance (>=5 tier; 3.0-tier variant measured catastrophic 239x239). Harness board-frame parity (worker-delivered, reviewed): conn_rot+outer_dir+facing threaded, 23/23 parity. usb_pd facing generalization (worker): NOT landed — kernel sim -1.0mm only, no present beneficiary; design + caveats recorded in scratchpad usb_pd_facing_result.md, future item. Rejections that mattered: usb_jtag seat-pull (385x318 explosion; audit-A defensible-trade verdict upheld). FINAL: 204x191, DRC 0, contract 148/0, fan-out 110/0, airwire 17319 (improved), all gates green, 48 targeted tests pass.
- FINAL GATE: full pytest suite 720 passed / 0 failed (311f120) — 7 pre-wire-world tests re-pinned to full-wire invariants (red-on-before -> holds-on-board; participants 23-wired/guarded-empty; bottom-convention worst re-measured).
- U3a FULL WIRE GREEN: 22 wired sheets, EXIT 0 (DRC 0, contract 0/106, fan-out 0/110 starved, silk 0, LAW-5/6 PASS) at 214x165. Convergence mechanized 6 engine defects, each measured on the emitted board, never softened a gate:
  1. zone-frame rotation: conn roots must be BUILT at their final LAW-6 rotation (connector_edge_rotation) or every solved adjacency shatters when placement rotates them (camera 3.7mm vs 8mm min_from).
  2. double-rotation: solver rot_out must EXCLUDE mating connectors (placement ADDS zone_extra_rot to conn_rot: 180+180=0 emitted, 8 connectors mouth-inward) — two emitter sites, both guarded.
  3. seat-line replication: the edge-seat overwrites the conn's perpendicular coordinate (pads at EDGE_PAD_CLEAR from the edge). The zone must put its outer boundary exactly there; the mouth overhangs off-zone as it overhangs off-board (DS1024 9mm mouth in-extents left ESD 13.5mm from pads; 11 violations, one mechanism).
  4. compose inboard clamp: clusters WITHOUT a connector must stay inboard of the aligned pad line (LDO cluster at min=0 rode the seat-line shift 1.0mm off Edge.Cuts).
  5. fan-out reach formula: max(0, margin-GRID) credit under-reserves whenever margin < GRID; straight need+GRID-margin (clamped at the end) — emitted blocks overlapped 0.18mm through the old credit.
  6. symmetric apron: a multi-pin member placed near a 2-pin NON-exempt crowder (shunt-anchored INA3221) must carry its OWN intelligent_need; only the reverse direction was enforced.
  Silk: declutter accepted exact tangency; gate re-read it as overlap at 1e-14. 0.02mm guard band in both placers (keep-site + relocation search).
- U3a: W1 (4 sheets) green after mechanizing the LAW-6 seat-sweep exclusion (DRC 28->0); coverage 19->14; FULL WIRE build launched (15 more sheets).
- U2a DONE: defect corpus 13/13. U4a implemented (board_verdicts.json).
- U1a-d DONE: project spec v1 (5 extractions), byte-identical e405097b.
- 2026-07-09: branch created off master 8b036b1; tracker initialized.
