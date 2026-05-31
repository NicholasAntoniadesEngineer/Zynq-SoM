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

## UPDATE 2 — power stamps landed (ERC 135→134); IC-edge labels need a router

DONE (committed eabc855, overlap stays 0/27):
- `edge_labels.power_drive_stamps` + `pipeline._assign_power_stamps`: one
  PWR_FLAG+rail-symbol stamp per power-symbol net, scanned into clear space,
  body-orientation computed so the connecting wire stays out of both bodies.
  Drives GND/+3V3/+2V5/+1V8/+5V/+12V/+VADJ/CHASSIS_GND. power_pin_not_driven 15→11.

INVESTIGATED & RULED OUT this pass (don't repeat):
- A* stub routing in the exposer (`route_astar`): REGRESSED overlap badly —
  route_astar uses a different clearance model than our validator-true bboxes,
  so its wires cross bodies/labels. Reverted.
- +VIN global-label+flag stamp: REGRESSED ERC (134→138). +VIN is rendered as
  LOCAL labels on the consuming sheets; a GLOBAL label won't merge with locals
  (different scope), so the flag drives a separate empty net. Reverted. To drive
  +VIN: either (a) make +VIN a power symbol (none exists in libs — would need a
  new zynq_eda:+VIN symbol like +VADJ), or (b) emit +VIN as GLOBAL labels
  everywhere it's consumed (change the exposer/labeler to use PlacedGlobalLabel
  for power-input rails not in POWER_SYMBOL_LIB_IDS), then one flag drives it.
- Multi-direction escape (try all 4 sides): only 8 of ~49 stuck pins become
  placeable. The rest are genuinely boxed in by dense module wiring + connectors.

REMAINING 134 = 123 pin_not_connected + 11 power_pin_not_driven:
- **123 pin_not_connected**: ~39 dense IC-edge pins (ethernet PHY ×8 blocked by
  the BS_COMMON bus, usb_pd FUSB302 left edge, uart, boot_switches) ×~3 instances.
  These need their label stubs ROUTED around obstacles. The right fix is a
  validator-faithful stub router (build a small A* that rasterises the SAME
  bboxes the validator measures — like core/route/grid.py's RouteGrid but
  reusing the validator's label/symbol bbox funcs), OR move these labels through
  labeler.py's lane interleaving (it already handles dense edges for connectors).
- **11 power_pin_not_driven**: all +VIN (see ruled-out note above for the two
  viable routes).

Best next step: make power-input rails NOT in POWER_SYMBOL_LIB_IDS (just +VIN)
emit as GLOBAL labels at every consumer + one PWR_FLAG → clears the 11 with low
risk. Then tackle the dense IC-edge stub routing for the 123.

## UPDATE 3 — CORRECTED diagnosis of the 11 power_pin_not_driven

Earlier I assumed the 11 were +VIN. WRONG. Verified via `kicad-cli sch erc
--format json`: the 11 are CONNECTOR power-input pins, e.g.:
  J1 Pin A4 [VBUS, Power input]   (×2)
  J1 Pin 3  [GND, Power input]
  J1 Pin 4  [VDD, Power input]
  J1 Pin 6  [VSS, Power input]
  J5A Pin 6 [GND_6, Power input], J5B Pin 1 [GND_1], J5B Pin 2 [+3V3], …
These are connector pins whose SYMBOL declares them Power-input type. They're
labeled with hier-labels (GND/+3V3/VDD…) by the labeler, but ERC still wants a
power-OUTPUT or PWR_FLAG on THAT pin's net. The GND/+3V3 PWR_FLAG stamps exist
(global power net) but evidently the connector pin's hier-label net isn't
binding to the power-symbol net, OR these pin NAMES (GND_1, VSS, VBUS) are
distinct power nets in KiCad's eyes.
  → INVESTIGATE: do these connector pins' hier-labels actually merge with the
    power:GND / power:+3V3 nets at the (sheet-pin-less) root? If KiCad treats a
    "Power input" pin's net by the pin's OWN name (GND_1) it won't merge with
    "GND". The legacy build handled this — compare its emitted netlist. Likely
    fix: lib_symbol_pin_type_overrides to make these connector power pins
    "passive" (they're just connector pads, not real power consumers), the same
    mechanism used for INA226 Vbus. That's per-connector-symbol, low-risk.

Tried & reverted (didn't help, the diagnosis above is why): flag-at-existing-
+VIN-label. +VIN was never the problem.

So the TRUE remaining work:
- 11 power_pin_not_driven: connector Power-input pads → override to passive
  (lib_symbol_pin_type_overrides per connector symbol) OR add PWR_FLAG per net.
- 123 pin_not_connected: dense IC-edge label stubs need routing (validator-
  faithful) — unchanged from UPDATE 2.
