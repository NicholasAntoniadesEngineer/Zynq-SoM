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
| U3a | Wire contracts: coverage 19 -> 0; cascade fixes mechanized | IN PROGRESS: W1 done (19->14, sweep fix landed); FULL WIRE (22 sheets) building |
| U4a | board_verdicts.json always-on structured verdicts | implemented; verify on next build |
| FIN | Deep retrospective vs all user asks + decided next steps | pending |

## Log
(newest first)
- U3a: W1 (4 sheets) green after mechanizing the LAW-6 seat-sweep exclusion (DRC 28->0); coverage 19->14; FULL WIRE build launched (15 more sheets).
- U2a DONE: defect corpus 13/13. U4a implemented (board_verdicts.json).
- U1a-d DONE: project spec v1 (5 extractions), byte-identical e405097b.
- 2026-07-09: branch created off master 8b036b1; tracker initialized.
