# Platform Rework — Overnight Retrospective (2026-07-28, branch `platform-rework`)

The mandate: *"work through the night until you have reached the final product we have
discussed... Once you think you are complete, remember everything I asked, deeply
analyse the progress, then decide the next steps."* This document is both.

## 1. What was asked (all of it)

1. **Optimize schgen so future board variants let AI tools really perform** — engine
   as mechanism, board as data; no backwards compatibility owed.
2. **Fable 5 solo** — every investigation and edit on this thread, no subagents.
3. **Principle 0** — the rendered image is the only proven ground truth. Any faster
   feedback loop must be validated against the visual loop before it is trusted.
4. **Two products**: schematics a senior engineer would sign (user: current ones are
   **golden references** — preserve, never "improve") and an **electronically logical
   PCB layout** like an advanced human engineer would produce.
5. **Routing struck** from scope; PCB *layout* absolutely in scope.
6. **Overnight**: single branch, no master merge until approval, no questions.

## 2. What landed (receipts)

### P1 — engine/project separation
- `carrier/project.json` + `schgen/core/project.py`: wired sheets, pilot sheets,
  module offset, module face anchors, reg-band prefixes are project **data**.
- **U1e/f**: `--project` CLI (env pre-parse before engine imports), `PROJECT_ROOT`
  indirection across 29 modules, loud failure on a missing spec.
- Byte-identity through the generalized machinery: `2f13efe8` exact.

### P2 — fast feedback under Principle 0
- `schgen board --no-render` fast gate loop (~4 min vs ~12).
- Defect corpus: 13 hermetic tests, 1.1 s — each defect class proven to fire its gate.
- 1 s/sheet solver harness used before every full build (caveat below).

### P3 — constraint-first placement (the campaign's core)
- **23/23 subsystem contracts placer-enforced** (was 4 wired / 18 inert / 1 violated).
- Final board: **EXIT 0 — DRC 0, placement contract 117 structures/0 violations,
  fan-out 110 subjects/0 starved, silk 0/0, LAW-5 ratsnest PASS (17688/18815 airwire
  budget), LAW-6 mech/model/spacing PASS, return-stitch PASS, deterministic
  (md5 `2f13efe8` twice)**, renders visually inspected (top: subsystem clusters +
  edge-flush connectors; bottom: passive banks under the SoM keepout only).
- Board size: 188×165 → **215×168 mm** (+16.4 % area). That is the measured price of
  *enforcing* 117 authored SI/PI structures + fan-out floors + seam reservations —
  every growth increment traceable to a specific enforcement round in the tracker.

Six engine defects were mechanized during convergence — each diagnosed by
instrumenting the emitted board, none by softening a gate (LAW 4):
1. Conn roots must be **built at their final LAW-6 rotation** or solved adjacency
   shatters when placement rotates them (camera: 3.7 mm vs an 8 mm min_from).
2. Solver `rot_out` must **exclude mating connectors** — placement *adds* zone rot to
   `conn_rot` (180+180→0: 8 connectors mouth-inward). Two emitter sites.
3. **Seat-line replication**: the edge-seat overwrites the connector's perpendicular
   coordinate (pads at `EDGE_PAD_CLEAR`). The zone boundary must sit exactly there;
   the mouth overhangs off-zone as it overhangs off-board (a DS1024's 9 mm mouth
   inside the extents put ESD members 13.5 mm from the pads — 11 violations, one
   mechanism).
4. **Compose clamp**: conn-less clusters must stay inboard of the aligned pad line
   (an LDO cluster normalized to 0 rode the seat shift 1 mm off Edge.Cuts).
5. **Fan-out reach formula**: `max(0, margin−GRID)` under-reserves whenever
   margin < GRID — adjacent blocks overlapped 0.18 mm. Straight `need+GRID−margin`.
6. **Symmetric apron**: a multi-pin member near a non-exempt 2-pin crowder must
   carry its own fan-out need (shunt-anchored INA3221 at 0.637 vs 1.0).

Plus: stage-path **generic-proximity solve** with **bound-priority displacement**
(restore-on-fail eviction), and a 0.02 mm silk guard band (float-tangency class).

One authoring correction: power_som EN clamp re-judged 3.0→6.0 mm (judgment tier)
after the displacement mechanic *proved* single-slot musical chairs — no legal
assignment exists at 3.0 against the datasheet-faithful core banks. Documented in
the contract with the measurement.

### U4a — machine-readable verdicts
`carrier/reports/board_verdicts.json` written on every build (all gates, structured).

### S-track — schematics
**Zero changes.** The golden references are untouched, as ordered.

## 3. Principle-0 compliance statement

Every convergence decision was made against the emitted board (positions parsed from
the `.kicad_pcb`, gate kernels re-run, renders eyeballed at the end). The fast
harness was used only to pre-screen; wherever harness and board disagreed the board
won and the discrepancy was root-caused (see caveat) rather than trusted.

## 4. What did NOT land (honest ledger)

- **U1g devkit_mini proof** — the zero-engine-edit second board. Path machinery is
  ready (see census below); what remains is *authoring*: `som_interface.json` subset,
  per-project subsystem binds, floorplan seeds, contracts. That is a design campaign,
  not a refactor, and doing it half-baked at 03:00 would violate Principle 0.
- **Harness conn_rot parity** — the 1 s/sheet synthetic model does not apply
  connector rotation, so edge sheets can false-fail there (camera/lcd showed pf=1
  while the board gate showed 0). Known, bounded, board always wins.
- **~30 residual literal sites** — `repo / "carrier"` in standalone dev-CLI blocks,
  argparse string defaults, firmware/vivado output paths. None are in the `board`
  build path; all should still be swept for U1g.
- **U2b** synthetic flow/facing harness — partially superseded by the defect corpus;
  not built.

## 5. Decided next steps (in order)

1. **U1g — devkit_mini**: author `devkit_mini/project.json` + `som_interface.json`
   subset (power, uart_bridge, usb_jtag, board_aux), bind modules reusing the
   portable `subsystems/` packages, floorplan seeds; build with
   `--project devkit_mini`; acceptance = all gates green with **zero engine edits**.
2. **Harness parity**: apply `connector_edge_rotation` in the synthetic model so the
   1 s loop stops false-failing edge sheets.
3. **Residual path sweep**: the ~30 literal sites above, then delete the census note.
4. **Contract authoring wave 2**: the remaining judgment-tier bounds re-examined the
   power_som way — displacement-proof before re-judging, measurement in the basis.
5. **Master merge** — only on explicit user approval (mandate honored: `platform-rework`
   is pushed, master untouched).

## 6. What the night proved about AI-driven layout

- **Constraint-first placement works end-to-end**: authored, datasheet-cited
  structures → solver → gate, with the gate kernel and the solver sharing frames,
  kernels and populations. Every one of the 6 defects above was a *parity* failure
  between those layers — the discipline "replicate the gate exactly or don't
  pre-empt it" is the platform's core invariant.
- **"Impossible" is almost always a defect**: 22 of 23 contracts that looked
  unplaceable were authoring/resolution/seed/frame bugs. The one true infeasibility
  (EN at 3.0) was *proven* infeasible by mechanism (displacement search), then
  re-judged with the proof attached — the correct division between LAW 4 (never
  soften to pass) and honest re-authoring.
- **The board is the only truth**: three separate times the synthetic model lied
  (frame conventions, missing conn_rot, missing seat). The platform's speed comes
  from fast loops; its correctness only ever came from the emitted artifact.
