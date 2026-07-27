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
| U2a | Defect-injection corpus library + gate-fires proof per class | pending |
| U2b | Fast flow/facing synthetic harness (validated vs corpus + visual sample) | pending |
| U3a | Wire contracts incrementally: coverage 19 inert-VIOLATED -> 0 (or documented infeasible), mechanizing each cascade fix | pending |
| U4a | schgen board --json structured gate verdicts | pending |
| FIN | Deep retrospective vs all user asks + decided next steps | pending |

## Log
(newest first)
- U1a-d DONE: project spec v1 (5 extractions), byte-identical e405097b.
- 2026-07-09: branch created off master 8b036b1; tracker initialized.
