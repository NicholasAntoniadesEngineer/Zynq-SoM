# OVERNIGHT IMPLEMENTATION PLAN — 2026-06-13/14

Durable execution record for the autonomous overnight run. The user approved
the **entire** investigation backlog (8-thread investigation, ~50 proposals)
via 12 decision questions, then went to bed with: *"work aggressively through
the night."* This file is the source of truth across context compactions —
update the checkboxes as units land.

## MANDATE (12 answers, 2026-06-13)

1. **Block diagram** → FULL professional rewrite (BD-1..8 + GAL-1).
2. **Tier-0 defects** → FIX ALL, including the 2 netlist/topology promotions
   (power_mon shunt split + HDMI-RX TMDS termination).
3. **Board HW** → ALL FOUR: board-ID EEPROM, RTC, QWIIC, supervisor+watchdog.
4. **Domains** → ALL FOUR: verification gates, generator+visual polish,
   developer experience, downstream/FPGA outputs.
5. **Big rocks** → ALL FOUR: bus notation (BUS-1), per-part rule engine,
   independent short/open CC proof gate, place.py split (ARCH-1).
6. **Commit policy** → commit+push every verified unit to
   `holistic-placement-rebuild`; fast-forward merge to `master` per completed
   track.
7. **Verify bar** → FULL regression before EVERY commit (board regen +
   selftest 44/44 + m1_rc + render eyeball + goldens).
8. **Strategy** → DEPTH-FIRST per track (finish+polish a track before next).
9. **Downstream artifacts** → ALL: BOM+CPL, Vivado TCL, PS device-tree,
   manifest.json.
10. **DFM/test docs** → ALL: TEST_PLAN.md, fiducials/tooling/ASSEMBLY_NOTES,
    chassis-GND star-bond, rev-A ICT plan.
11. **Sourcing** → ALL: HX5008 2nd-source, ALT_LCSC+stock-floor gate,
    lifecycle/EOL snapshot, inline-parts→folders + symbol fixes + part_gen
    regression tier.
12. **When done** → KEEP GOING: Tier-3 polish, then re-investigate, then keep
    implementing. Don't stop until the user is back.

## STANDING CONSTRAINTS (must hold for every relevant unit)

- **C1 — manual power enable on ALL new HW.** Every new hardware block
  (EEPROM, RTC, QWIIC, supervisor) sits behind a manual/DIP power enable using
  the existing gated-module idiom (SY6280 / module-gate), exactly like the
  current gated rails. No always-on additions without a gate.
- **C2 — watchdog must NOT reset during power-up.** The supervisor/watchdog is
  armed only AFTER rails are stable; its RESET must never fire during the
  bring-up ramp. Gate it + sequence its arm so a cold boot is never reset by
  it.
- **C3 — Zynq SoM chip may change later** (availability). Do NOT build
  chip-swap machinery now (carrier must be fully defined first), but avoid
  hard-coupling to XC7Z020 in ways that are painful to undo. Keep the device
  id sourced live from the SoM project (already the case in xdc.py), don't
  scatter the literal.
- **C0 — the LAWS still rule.** LAW 0 electrical integrity (prove the netlist,
  no shorts/opens), LAW 1 visual correctness (zero overlap/crossing), LAW 4
  never soften a gate. New geometry (bus notation) merges electrically only via
  alias labels proven by the kicad-cli netlist gate.

## EXECUTION DISCIPLINE

- Single writer to the working tree (me). Parallel agents/workflows only for
  DISJOINT add-only work (new subsystems, new generator modules, new gates,
  new parts/ folders, docs) in isolated worktrees, harvested sequentially.
  NEVER blind `git diff | apply`; NEVER `find -print0 | grep -z | xargs` on
  macOS.
- Full regression before every commit. Commit+push per unit. Merge to master
  per completed track (fast-forward).
- Depth-first: finish a track to 100% (incl. render eyeball for visual work)
  before starting the next.

## BUILD-SPEED NOTE (why PERF goes first)

Baseline: `selftest` ~68s, `board` ~172s (mostly serial kicad-cli + an
hdmi_rx escape-router quadratic). With full-regression-every-commit across
dozens of units, this dominates the night. **PERF-2 (parallelize kicad-cli) +
PERF-1 (memoize the hdmi_rx hotspot) are done FIRST** so every later
regression is fast (target board <60s). Both behavior-preserving — verified by
byte-identical goldens + the determinism check.

---

## TRACKS (priority order; depth-first)

### TRACK 0 — SETUP
- [x] Baseline selftest PASS 44/44 + determinism
- [ ] Baseline board build green + timing (bg) ; write plan + memory ; commit plan

### TRACK PERF — build speed (do first)
- [ ] PERF-2 parallelize per-sheet kicad-cli (netlist/ERC/render) via ThreadPool, deterministic sorted aggregation (__main__.py, board.py)
- [ ] PERF-1 memoize foreign-geometry + PinRef→Net index in _bfs_escape/_cell_free (place.py)

### TRACK DEFECTS — Tier-0 (fix all)
- [ ] DEF-1 3D model offset unit bug + add_part assertion + regen FUSB302/TPS26631/AO3400A/INA3221 (part_gen.py)
- [ ] DEF-2 thermal/EP-pad solder-paste relief ~60% windowed (part_gen _pad_sx)
- [ ] DEF-3 forbid footprint-less BOM parts (gate) + backfill (model/__main__)
- [ ] DEF-4 `schgen link` clobber guard — tempdir/refuse unless whole-board or -o (link.py cmd_link) [== DX-2 P3]
- [ ] DEF-5 power_mon shunt-rail split: power.py emits +VIN_SYS/+5V_REG/+3V3_REG/+1V8_REG; remove 4 TP waivers (power.py, power_mon.py)
- [ ] DEF-6 HDMI-RX TMDS sink termination 8×49.9R + AVCC island + caps on som_j2 sheet (hdmi_rx.py/som_j2.py + place if needed)

### TRACK BLOCKDIAG — full rewrite (acute)
- [ ] BD-1 layered L→R DAG layout + crossing reduction (diagram.py)
- [ ] BD-2 aggregate 243 peer edges → per-pair count edges
- [ ] BD-3 distinct per-edge SoM anchors (tall SoM column)
- [ ] BD-4 orthogonal Manhattan routing + bundling
- [ ] BD-5 legend + power-vs-signal color from ptype.kind
- [ ] BD-6 label grammar/typography + net-group labels
- [ ] BD-7 subsystem clusters
- [ ] BD-8 landscape canvas sizing + GAL-1 README width cap

### TRACK VERIFY — gates + automated testing
- [ ] VER-1 design-rule completeness gate (decoupling/i2c-pullup/reset-RC/floating-input) + waivers + board hook (verify/design_rules.py)
- [ ] VER-2 per-device thermal Tj gate (powertree RegSpec rth_ja+Ta+Tj_max + table)
- [ ] VER-3 mutation classes for new + untested gates (selftest.py)
- [ ] VER-4 [BIG] independent connected-components short/open proof gate + mutants (verify/cc_gate.py)

### TRACK DEVEX — dev experience + automated testing
- [ ] DX-1 pytest unit-test layer for engine primitives (tests/) [HIGH — user emphasis]
- [ ] DX-2 authoring UX: P1 clean CLI errors, P2 unassigned-by-name, P4 list/pins, P5 bulk-NC, P6 footprint-validate, P7 build-time link check, P8 scaffolder+DESIGN.md path, P10 unify loaders
- [ ] DX-3 DEBT-1 PlacedDesign.from_placement factory + DEBT-3 rename _DRIVER_ETYPES
- [ ] DX-4 [BIG] place.py split into template modules behind registry (AFTER DX-1)

### TRACK GENPOLISH — visual fidelity
- [ ] GP-1 TITLE-1 populated title block (emit.py)
- [ ] GP-2 CUE-1 net-class stroke cues
- [ ] GP-3 SIZE-1 A2/A1 sheet-size ladder
- [ ] GP-4 LABEL-1 directional label shapes
- [ ] GP-5 IDIOM-1 broaden templates / relax regulator shared_ok
- [ ] GP-6 [BIG] BUS-1+BUS-2 bus notation (RGB888/FMC/SDIO) — alias-merge, LAW 0
- [ ] GP-7 MULTIUNIT-1 multi-unit symbols

### TRACK DOWNSTREAM
- [ ] DS-1 assembly-ready BOM enrich (MPN/datasheet/Basic-Ext) + JLC CPL cpl_jlc.csv
- [ ] DS-2 Vivado create_project.tcl (device live-sourced — C3)
- [ ] DS-3 Zynq PS device-tree fragment carrier_pl.dtsi
- [ ] DS-4 manifest.json integration spine

### TRACK SOURCING
- [ ] SRC-1 HX5008 second-source committed alternate
- [ ] SRC-2 ALT_LCSC field + stock-floor preflight gate
- [ ] SRC-3 lifecycle/EOL + stock/price snapshot capture (part_gen)
- [ ] SRC-4 inline 5 schgen: parts → parts/ folders + symbol-name preservation (P5) + part_gen regression tier (P6)

### TRACK BOARDHW — new hardware (C1 gated; C2 watchdog post-stable)
- [ ] HW-1 board-ID EEPROM 24AA025E48 EUI-48 @0x50 (gated rail)
- [ ] HW-2 RTC RV-3028-C7 + CR2032 (gated rail)
- [ ] HW-3 QWIIC on dedicated gated PL-fabric I2C
- [ ] HW-4 supervisor + watchdog (gated; armed only after rails stable)
- [ ] HW-* parts/ folders for new parts + downstream regen (firmware I2C map)

### TRACK RULE-ENGINE — [BIG] large capability
- [ ] RE-1 part_gen captures RATINGS (V/I/P/tol/dielectric/temp)
- [ ] RE-2 per-part RULES (derate / pullup_window / fb math)
- [ ] RE-3 `schgen rulecheck` gate (net voltage from power tree × rules) + board hook
- [ ] RE-4 seed MLCC derating ≥50% + pull-up window + buck FB; + mutants

### TRACK DFMDOCS
- [ ] DOC-1 TEST_PLAN.md (SPICE limits + TP pads + DIP seq)
- [ ] DOC-2 fiducials + tooling holes + ASSEMBLY_NOTES.md (from floorplan outline)
- [ ] DOC-3 chassis-GND star-bond explicit, gate-checked requirement
- [ ] DOC-4 rev-A ICT / flying-probe plan

### TRACK TIER3 — polish then re-investigate (keep going)
- [ ] symbol quality P5 deepening, datasheet bundle PARTS.md, PCB stub, boot/heartbeat LEDs, FILL-1, FP-1/2, RND-1, GAL-2, REUSE-1
- [ ] fresh investigation round → next wave → keep implementing

---

## PROGRESS LOG (newest first)
- 2026-06-13: investigation complete (8 threads); 12 decisions captured; baseline green; plan written. Starting TRACK PERF.
