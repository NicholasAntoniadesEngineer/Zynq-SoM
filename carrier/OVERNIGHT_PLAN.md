# OVERNIGHT IMPLEMENTATION PLAN — 2026-06-13/14

Durable execution record for the autonomous overnight run. The user approved
the **entire** investigation backlog (8-thread investigation, ~50 proposals)
via 12 decision questions, then went to bed with: *"work aggressively through
the night."* This file is the source of truth across context compactions —
update the checkboxes as units land.

## STATUS @ overnight (newest commits on master, fast-forwarded)

LANDED ON MASTER (each: full regression — board PASS 26 sheets + selftest
44/44 + m1 + determinism — before commit):
- PERF-2 parallel kicad-cli (172s→142s) · PERF-1 PinRef→Net index
- DEF-1 3D-model-offset bug (4 parts) · DEF-2 thermal-pad paste relief (5) ·
  DEF-3 default footprints + BOM footprint gate · DEF-4 link clobber guard ·
  DEF-6 HDMI-RX TMDS termination (new hdmi_rx_term sheet)
- BLOCK DIAGRAM full rewrite (the acute item) — layered DAG, clusters, legend,
  landscape; the unreadable strip is gone
- DOWNSTREAM: 4 new generators (Vivado TCL, PS device-tree, manifest.json,
  TEST_PLAN.md) + CLI subcommands
- DEVEX: pytest unit-test layer (147 cases) · DEBT-3 constant rename

ALSO LANDED: verification gates — design-rule completeness + per-device
thermal Tj (both hooked into `schgen board`, waivable, with CLI).

⚠ REVIEW ITEMS FOR YOU (surfaced by the new gates / deferred work):
1. THERMAL — the 3 TPS54302 bucks (U1/U2/U4, SOT-23-6 no exposed pad) are
   thermally layout-critical: Tj over the guard under the conservative model;
   waived + documented in carrier/research/thermal_bucks.md. Confirm RθJA by
   thermal sim / bench at bring-up, or move U1 (the hottest, 20 V→5 V @ 2.8 A)
   to an exposed-pad buck. This is a genuine margin call worth your eyes.
2. DEF-5 power_mon shunt split still deferred (telemetry reads across an open
   until the firmware shunt-walk + power-sheet decongest land).

DEFERRED / BIG-ROCKS still to do: DEF-5 power_mon shunt split (needs firmware
shunt-walk + power-sheet decongest), DS-1 BOM+CPL, bus notation, place.py
split, per-part rule engine, board HW (EEPROM/RTC/QWIIC/supervisor — all C1
gated), sourcing (HX5008 2nd-src/ALT_LCSC), GENPOLISH (title block/net-class
cues/sizing), remaining DFM docs, mutation classes + cc-gate.

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
- [x] Baseline board build green + timing (~172s) ; plan + memory ; commit plan (94a2c4e)

### TRACK PERF — build speed (do first)  [DONE]
- [x] PERF-2 parallelize per-sheet kicad-cli (ThreadPool, names-order verdicts) — 172s→142s (e7eebbf)
- [x] PERF-1 PinRef→Net index in _Engine (kills net_of quadratic; modest wall-time, kept) (8ea4542)

### TRACK DEFECTS — Tier-0 (fix all)
- [x] DEF-1 3D model offset unit bug — implausible offset reset to 0 + regen 4 parts (d576e26)
- [x] DEF-2 thermal/EP-pad windowed paste relief ~60% (5 footprints) (2399432)
- [ ] DEF-3 forbid footprint-less BOM parts (gate) + backfill (model/__main__)
- [x] DEF-4 `schgen link` clobber guard — partial link -> tempdir (186d87b) [== DX-2 P3]
- [~] DEF-5 DEFERRED to a big-rock effort. The 12-rename shunt split is
      electrically correct (net membership verified) but breaks two consumers:
      (1) the power-sheet ROUTER fails — the 4 new *_REG/+VIN_SYS rail symbols
      over-densify the most complex sheet (54 parts/29 nets), router exhausts 8
      expansions on an EN_5V_SOM vs GND contention (NOT a fit/size issue, so
      SIZE-1/A2 won't help); (2) firmware.py power-tree walk gets stuck — it
      chains regs directly and does not traverse the INA3221 series shunts.
      UNBLOCK PLAN: (a) firmware.py walk must hop through RS1-RS4 shunts;
      (b) decongest power.py by splitting the +5V_SOM/U4 always-on buck into
      its own sheet (power_som.py) — frees ~12 parts AND removes the contention
      region; (c) then land the 12 renames + power_mon waiver text. Reverted to
      green (186d87b).
- [x] DEF-6 HDMI-RX TMDS sink termination — NEW sheet hdmi_rx_term.py: 8×49.9R
      (C114625) from HDMI_RX_*_P/N to AVCC=+3V3. LINK PASS (3-way TMDS merge
      with hdmi_rx + som_j2), powertree +64mA OK, render clean. The 100n/1u
      AVCC bypass is a documented LAYOUT NOTE (not netlisted): the placer
      cannot anchor a rail-to-rail cap with no host part on an IC-less sheet
      ("no topology pattern matched"). >>> PLACER FINDING (-> GENPOLISH/ARCH):
      the placer has no pattern for standalone rail-decoupling caps (cap whose
      both pins are power rails, no IC). A small robustness fix (place such
      caps on the rail trunk / next to the rail power-symbol) would let DEF-6
      carry its bypass caps AND helps any future rail-bypass-only content.

### TRACK BLOCKDIAG — full rewrite (acute)  [DONE — worktree agent, 8 iters]
- [x] BD-1..8 + GAL-1 ALL landed in one diagram.py rewrite: layered L→R DAG with
      barycentre crossing reduction, peer-edge aggregation (per-pair count +
      dominant-kind), tall central SoM spine with distinct per-edge anchors,
      orthogonal gutter routing with unique per-edge lanes, ptype.kind colour +
      legend, fixed label grammar ('N nets · group'), subsystem clusters,
      landscape 2348×716 canvas (was 860×2580 strip), README embeds capped at
      width=900. Render rasterised + eyeballed — clean, readable, professional;
      the acute "unreadable" complaint is resolved.

### TRACK VERIFY — gates + automated testing  [VER-1/2 done, worktree agents]
- [x] VER-1 design-rule completeness gate (verify/design_rules.py): decoupling
      per IC supply pin / i2c pull-up / reset-RC / floating-strap, pin function
      inferred by NAME, model-only, waivable + board hook + `schgen design-rules`
      CLI. Findings on the current board: 0 missing decap, 2 hdmi_tx DDC pulls
      (waived: TPD12S016-integrated), 2 GPIO/internal-pull resets (waived).
- [x] VER-2 per-device thermal Tj gate (schgen/thermal.py): Tj=Ta+Pd*RthJA per
      device + waivable + board hook + `schgen thermal` CLI. >>> SURFACED A REAL
      ITEM: the 3 TPS54302 bucks (U1/U2/U4, SOT-23-6 no-EP) exceed the Tj guard
      under the conservative bare-package model — WAIVED as layout-critical +
      REVIEW-FLAGGED in carrier/research/thermal_bucks.md (confirm RthJA by
      thermal sim/bench at bring-up, else switch U1 to an exposed-pad buck).
- [ ] VER-3 mutation classes for new + untested gates (selftest.py)
- [ ] VER-4 [BIG] independent connected-components short/open proof gate + mutants (verify/cc_gate.py)

### TRACK DEVEX — dev experience + automated testing
- [x] DX-1 pytest unit-test layer (schgen/tests/, 147 cases ~8s, worktree agent) — c92d7c4 [HIGH — user emphasis]
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

### TRACK DOWNSTREAM  [3/4 + TEST_PLAN done via parallel worktree workflow]
- [ ] DS-1 assembly-ready BOM enrich (MPN/datasheet/Basic-Ext) + JLC CPL cpl_jlc.csv  <-- still TODO
- [x] DS-2 Vivado create_project.tcl (schgen/vivado.py; device live-extracted via extract_zynq) + CLI + board hook
- [x] DS-3 Zynq PS device-tree fragment (schgen/devicetree.py -> carrier/firmware/carrier_pl.dtsi) + CLI + hook
- [x] DS-4 manifest.json integration spine (schgen/manifest.py; 24 rails/i2c/gpio + 43 artifact sha256) + CLI + hook
- [x] DOC-1 TEST_PLAN.md (schgen/testplan.py; spice limits + TP pads + DIP stages) + CLI + hook  [also a DFMDOCS item]
      All 4 built by a worktree-isolated parallel workflow, content harvested,
      hooked into cmd_board + registered as `schgen vivado|devicetree|manifest|
      testplan` CLI subcommands. board PASS, deterministic, selftest 44/44.

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
