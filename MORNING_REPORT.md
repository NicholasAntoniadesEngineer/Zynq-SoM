# Overnight run — morning report (2026-06-14)

Autonomous overnight session summary. Detailed tracker:
[carrier/OVERNIGHT_PLAN.md](carrier/OVERNIGHT_PLAN.md). **Everything below is on
`master`** (fast-forwarded, ~18 commits), each gated by a full regression —
board PASS 26 sheets + selftest **53/53** + m1 + byte-determinism + pytest
**154** — before it landed. Working tree clean.

## What landed (by track)

| Track | What |
|------|------|
| **Block diagram (your #1)** | Full rewrite — the unreadable 860×2580 strip → a clean **layered landscape system map**: subsystem clusters, a tall central SoM spine, a legend, per-edge type-colouring + counts. |
| **Tier-0 defects** | **DEF-1** 3D-model-offset bug (4 parts a metre off); **DEF-2** thermal-pad **paste relief** (5 parts); **DEF-3** default footprints + a **BOM footprint gate**; **DEF-4** `schgen link` clobber guard; **DEF-6** **HDMI-RX TMDS termination** (new sheet). |
| **Downstream** | 4 new generators + CLI: **Vivado `create_project.tcl`**, **PS device-tree** `carrier_pl.dtsi`, **`manifest.json`** spine, **`TEST_PLAN.md`**. |
| **Verification** | **pytest** unit layer (154 cases, ~8 s) · **design-rule completeness** gate · **per-device thermal Tj** gate · **+9 mutation classes** proving the model-only gates bite (44→53). |
| **Generator polish** | **Title block** populated on every sheet (was blank). |
| **Sourcing** | `ALT_LCSC` second sources + a **procurement stock-floor** in preflight (the HX5008 stock-10 landmine now WARNs); unit-tested. |
| **Build/engine/DFM** | `schgen board` parallelised (172→142 s); `_DRIVER_ETYPES` footgun renamed; `ASSEMBLY_NOTES.md` (fiducials/tooling/chassis-GND star/silkscreen). |

In flight (isolated worktree agent): **VER-4** connected-components short/open
gate — an independent oracle vs kicad-cli. Will be integrated or handed off as
a verified artifact.

## ⚠ Review items — your eyes wanted

1. **TPS54302 buck thermals (real, surfaced by the new thermal gate).** U1/U2/U4
   (SOT-23-6, no exposed pad) exceed the Tj guard under the conservative
   bare-package model. Waived as layout-critical + documented in
   [carrier/research/thermal_bucks.md](carrier/research/thermal_bucks.md):
   confirm RθJA by thermal sim / bench at bring-up, or move U1 (hottest, 20 V→5 V
   @ 2.8 A) to an exposed-pad buck. A genuine margin call.
2. **DEF-5 power_mon shunt split — deferred.** Per-rail telemetry reads across an
   open until two coupled changes land (firmware power-tree walk must traverse
   the INA3221 shunts; the power sheet must be decongested, cleanest by splitting
   the +5V_SOM/U4 buck to its own sheet). A 3-part big-rock, not a quick fix.

## Constraints honoured

- New HW (EEPROM/RTC/QWIIC/supervisor) **not yet added** (deferred); when added
  it will be **manual-power-enable gated (C1)** and the watchdog **armed only
  after rails are stable (C2)**.
- Device id stays **live-sourced** from the SoM project (C3).

## Deferred (big-rocks / risk — better with your review, not done overnight)

Bus notation, per-part rule engine, `place.py` split, board HW additions,
BOM+CPL (DS-1), part lifecycle/EOL snapshot, inline-parts→folders. All tracked
with rationale in the plan.

## How to verify

```
python3 -m schgen board          # 26 sheets, every gate PASS
python3 -m schgen selftest       # 53/53 mutants killed + byte-determinism
python3 -m pytest schgen/tests/  # 154 unit cases
python3 -m schgen thermal        # the Tj gate (the buck review item)
python3 -m schgen design-rules   # the completeness gate
```
