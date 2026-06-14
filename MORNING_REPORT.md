# Overnight run — morning report (2026-06-14)

One-page summary of the autonomous overnight session. Detailed tracker:
[carrier/OVERNIGHT_PLAN.md](carrier/OVERNIGHT_PLAN.md). Everything below is on
**`master`** (fast-forwarded), each commit gated by a full regression (board
PASS 26 sheets + selftest 44/44 + m1 + determinism + pytest) before landing.

## TL;DR — what landed

| Area | What |
|------|------|
| **Block diagram (your #1 item)** | Full rewrite — the unreadable 860×2580 strip is now a clean **layered landscape system map**: subsystem clusters, a tall central SoM spine, a legend, per-edge type-colouring + counts. |
| **Tier-0 defects** | 5 of 6 fixed: 3D-model-offset bug (4 parts), thermal-pad **paste relief** (5 parts), **BOM footprint gate** + default footprints, `schgen link` clobber guard, **HDMI-RX TMDS termination** (new sheet). DEF-5 (power_mon shunt split) deferred — see review items. |
| **Downstream (close the loop)** | 4 new generators + CLI: **Vivado `create_project.tcl`**, **PS device-tree** `carrier_pl.dtsi`, **`manifest.json`** integration spine, **`TEST_PLAN.md`** acceptance checklist. |
| **Verification (your testing emphasis)** | **pytest unit layer** (147 cases, ~8 s) + two new gates: **design-rule completeness** (decoupling/i2c-pull/reset-RC/strap) and **per-device thermal Tj**. |
| **Build speed** | `schgen board` parallelised (172 s → ~142 s). |
| **Engine hygiene / DFM** | `_DRIVER_ETYPES` footgun renamed; `ASSEMBLY_NOTES.md` (fiducials/tooling/chassis-GND star/silkscreen). |

## ⚠ Review items — your eyes wanted

1. **TPS54302 buck thermals (real, surfaced by the new thermal gate).** U1/U2/U4
   (SOT-23-6, no exposed pad) exceed the Tj guard under the conservative
   bare-package model. **Waived as layout-critical + documented in**
   [carrier/research/thermal_bucks.md](carrier/research/thermal_bucks.md):
   confirm the effective RθJA by thermal sim / bench at bring-up, or move U1
   (hottest, 20 V→5 V @ 2.8 A) to an exposed-pad buck. Genuine margin call.
2. **DEF-5 power_mon shunt split — still deferred.** Per-rail current telemetry
   reads across an open until two coupled changes land (firmware power-tree
   walk must traverse the INA3221 shunts; the power sheet must be decongested,
   cleanest by splitting the +5V_SOM/U4 buck to its own sheet). It's a 3-part
   big-rock, not a quick fix — held to avoid blocking the other defects.

## Constraints honoured

- New HW (EEPROM/RTC/QWIIC/supervisor) is **not yet added** — see deferred; when
  added it will be **manual-power-enable gated (C1)** and the watchdog **armed
  only after rails are stable (C2)**.
- Device id stays **live-sourced** from the SoM project (C3) — no XC7Z020
  hard-coding scattered in.

## Deferred (big-rocks / risk — not attempted overnight)

Bus notation, per-part rule engine, `place.py` split, independent
connected-components short/open gate, board HW additions, sourcing ALT_LCSC +
stock-floor, generator title-block/net-class polish, BOM+CPL (DS-1). All
tracked with rationale in the plan. (This list shrinks as the run continues.)

## How to verify

```
python3 -m schgen board        # full board: 26 sheets, all gates PASS
python3 -m schgen selftest     # 44/44 mutants killed + byte-determinism
python3 -m pytest schgen/tests/  # 147 unit cases
python3 -m schgen thermal      # the new Tj gate (the buck review item)
python3 -m schgen design-rules # the new completeness gate
```
