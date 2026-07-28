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
| U1e | ModuleGeom: module pcb/interface paths from spec (generalize SomGeom entry) | pending |
| U1f | --project CLI + CARRIER path resolution via project root | pending |
| U1g | devkit_mini second-project proof: green board, ZERO engine edits | pending |
| U2a | Defect-injection corpus library + gate-fires proof per class | DONE (13 tests, 1.1s) |
| U2b | Fast flow/facing synthetic harness (validated vs corpus + visual sample) | pending |
| U3a | Wire contracts: coverage 19 -> 0; cascade fixes mechanized | 22/22 GREEN (EXIT 0, all gates, 214x165); power_som (23rd) wiring in build |
| U4a | board_verdicts.json always-on structured verdicts | implemented; verify on next build |
| FIN | Deep retrospective vs all user asks + decided next steps | pending |

## Log
(newest first)
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
