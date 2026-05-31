# Convergent layout engine — status (Stages A–E)

Branch: `holistic-placement-rebuild`. `main` stays at the legacy shippable build.

## DONE — placement + routing + intra-sheet labels (27/27 visually clean)

The new engine is **wired into the production pipeline** (`pipeline.run_carrier`
now calls `route_sheet`, not legacy `place_block`; legacy kept as survey-only
fallback). Full `--board carrier` build runs end-to-end through root sheet +
BOM + IO emitters.

- **Stage A — `core/layout/module.py`** (`solve_module`): per-IC clean-by-
  construction module. Seeds a cell per external part near its `from_pin`,
  projects to ≥2.54 mm with `separate.remove_overlaps` (IC fixed), pulls in,
  routes intra-module trunks with the cached-grid A* router, freezes a `Module`
  (symbols/wires/junctions/labels/ports). Merge nets (BS_COMMON) get one shared
  label; rails/GND get power symbols.
- **Stage B — `core/layout/arrange.py`** (`arrange_block`): each frozen module +
  connector = one rigid rect, spread into page-filling regions
  (`regions.partition_and_assign`, connectors edge-biased), projected to ≥2.54 mm.
  Modules move only by rigid translation ⇒ cannot re-crowd. Connector wide
  part-name Value text shifted BELOW the body (clear of pin rows).
- **Stage C — `core/route/route_sheet.py` + `route_module.py`** (+ a parallel
  `core/route/grid.py` I wrote, now redundant with route_module — candidate for
  deletion): assembles the sheet, re-routes dense modules with bounded grid A*
  (`astar.route_astar`) on a per-PRIMITIVE obstacle set, no-regression guard.
  `_dedupe_overlaps` unions each net's segments into non-overlapping maximal
  runs (kills same-net overshoots, e.g. BS_COMMON). `_junctions` detects T-taps.
- **Stage D — `core/layout/labeler.py`** (`label_connectors`): point-feature
  lane-interleaving labels for every connector `pin_to_net` pin (hier-label for
  declared external nets, local label otherwise) + stub wire. Render-is-judge
  min-clash fallback.

**Gate met:** `validate_overlap(strict=False)` = **0 on all 27 sheets at 2.54 mm**
(zero overlap + zero crowding). bounds = 0. Renders reviewed (power, usb_pd,
usbc_otg, ethernet, jtag_swd) — clean, wire-heavy, hand-drawn quality.

## TODO — Stage E: cross-sheet ELECTRICAL contract (ERC). 489 errors.

The engine produces visually-clean sheets but does NOT yet emit the cross-sheet
net contract the legacy planner did. ERC breakdown (from
`boards/carrier/validation_report.md`):

- **474 `pin_not_connected` + 402 `hier_label_mismatch`** — ROOT CAUSE: the
  engine emits hier-labels ONLY for connector `pin_to_net` pins. It MISSES
  declared `external_nets` that originate on **IC pins** or need a sheet-edge
  stub: e.g. `power` emits 0 hlabels but declares 5 (+1V8/+2V5/+3V3/+VIN/GND);
  `ethernet` 3/13 (MDI pairs, GND, +3V3 missing); `boot_switches` 2/7 (boot-mode
  straps). Connector-only sheets are ~27/28 (just GND/+3V3 missing).
  → FIX: emit a hier-label for EVERY `block.external_nets` entry, attached to its
  pin/wire (IC pin tip, connector pin, or a power/GND stub). Mirror legacy
  `plan._emit_edge_label_hlabels` + `_emit_orphan_external_net_hlabels`.
- **~31 `power_pin_not_driven` / `pin_not_driven`** — the engine doesn't emit
  PWR_FLAGs / the GND drive stamp / power-rail taps the legacy planner did
  (`plan._emit_pwr_flags`, `_emit_gnd_drive_stamp`, `_emit_power_rail_taps`).
  → FIX: port those, attaching a PWR_FLAG to each undriven power-input net and
  one GND drive stamp on the `power` block.
- **28 `unconnected_wire_endpoint` + 2 `label_dangling`** — stub wires whose far
  end has no label/pin, or labels not on a wire. Likely fixed as a side effect of
  the hier-label completion; re-measure after.

Verification loop:
- per-sheet: `python -m zynq_eda.core.render.reconcile --block <name> --render-dir /tmp/x`
- overlap survey: the snippet in /tmp/modD/sheets3.log (route_sheet + validate_overlap, all 27)
- ERC: `python -m zynq_eda --board carrier` (strict; halts on overlap, then runs ERC)
- run from `eda/`, `PYTHONPATH=src`, interp `../.venv/bin/python`. Output dir is
  REPO-ROOT `boards/carrier/` (not under eda/).

Done bar: 27/27 overlap=0 (MET) AND ERC clean (TODO) AND renders reviewed.

## UPDATE — Stage E in progress: ERC 489 → 135

DONE this pass (all committed, overlap stays 0/27):
- `edge_labels.no_connect_markers` — NC on every spare connector pad + NC IC pin.
  Cleared 330 `pin_not_connected`.
- `edge_labels.expose_ic_pin_nets` — attaches each floating IC pin's net
  (power symbol / hier-label / local label) on a clearance-checked outboard
  stub. True page-side escape, validator-own bboxes, full power-symbol footprint.
  Floating IC pins 72 → 39.
- `route_sheet` feeds module labels into the obstacle set (fixed the usb_pd
  +VIN/CC2 clash; root cause was module labels missing from `occupied`).

REMAINING 135 ERC errors = 120 `pin_not_connected` + 15 `power_pin_not_driven`:
- **120 pin_not_connected** = 39 IC pins the exposer's straight-outboard walk
  couldn't clear, ×~3 (root + sub-sheet instances). Concentration:
  ethernet 17 (PHY MDI pairs, left edge, blocked by the BS_COMMON bus loop),
  usb_pd 10, uart_bridge 5, boot_switches 4, others ≤2.
  → FIX: route these dense IC-edge labels through the LANE-INTERLEAVING logic
    in `labeler.py` (same as connectors) instead of the exposer's simple walk,
    OR let the exposer try perpendicular offset + longer reach when straight
    outboard is blocked. The 8 ethernet PHY pins are 5.08 mm pitch so they fit
    vertically — they just need to escape PAST the bus.
- **15 power_pin_not_driven** — no PWR_FLAG / GND drive stamp emitted. Port
  legacy `plan._emit_pwr_flags` + `_emit_gnd_drive_stamp` + `_emit_power_rail_taps`:
  one PWR_FLAG per undriven power-input net, one GND drive stamp on `power`.

The strict build halts on ERC (not overlap — overlap is 0). Done bar:
27/27 overlap=0 (MET) AND ERC=0 (135 to go) AND renders reviewed (MET for placement).
