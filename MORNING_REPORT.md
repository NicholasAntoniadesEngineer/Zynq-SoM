# Overnight run — morning report (2026-06-14)

Autonomous overnight session summary. Detailed tracker:
[carrier/OVERNIGHT_PLAN.md](carrier/OVERNIGHT_PLAN.md). **Everything below is on
`master`** (fast-forwarded, ~28 commits), each gated by a full regression —
board PASS **29 sheets** + selftest **53/53** + m1 + byte-determinism + pytest
**178** — before it landed. Working tree clean.

## Continuation tracks (after the first draft)

1. **VERIFY — independent CC short/open gate.** A 2nd oracle, disjoint from
   kicad-cli (net-blind union-find over the emitted geometry); agrees pin-for-
   pin on all sheets. The board is now electrically proven by two code paths.
2. **Board HW — ALL FOUR blocks** (see the dedicated section below).
3. **Two adversarial re-investigation audits** (11 dimensions, ~30 agents).
   Every finding independently re-verified — several confident "HIGH/CRITICAL"
   findings were FALSE POSITIVES whose fixes would have *introduced* bugs, and
   are documented-rejected (a DSHP04 mis-wire that never enables the rail; a
   non-existent PCA9306 EN float; an ~11 µA EN back-feed; an over-stated USBLC6
   "ineffective" claim). REAL fixes landed: firmware I2C-map completeness
   (ID-EEPROM/RTC/FMC addresses, EEPROM strap-derived so a mis-strap trips the
   collision check); a **VCCO bank-rail drift gate** (xdc IOSTANDARD map vs
   som_conn_gen — a C3 safety net); QWIIC ESD on its own sheet with the clamp
   referenced to always-on +3V3; the RTC primary-cell/trickle-charger safeguard
   elevated into the firmware contract; DFM/assembly notes; a derived bring-up
   "Stage 6 — board services". ~30 new pytest cases lock it all.

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

## Board HW — ALL FOUR landed (was deferred; now done)

Two new sheets, **board_aux** (gate + PCA9306 I2C isolator) and **board_services**
(EEPROM + RTC + watchdog + QWIIC), split so neither defeats the placer. board
PASS @ **28 sheets**, every gate green, determinism + preflight PASS (+$4.56/bd).

- **ID-EEPROM** 24AA025E48 — factory **EUI-48 MAC** for the RJ45 (0x51).
- **RTC** RV-3028-C7 — integrated DTCXO (no crystal) + CR1220 backup (0x52).
- **Watchdog** TPS3823-33 + **QWIIC** expansion.
- **C1**: all on the default-OFF, DIP-gated +3V3_AUX (SY6280). **C2**: watchdog
  unpowered at power-up + WDI-float-disable + RESET# as a firmware-mediated PL
  event — *three* guards, never a hard POR. **C3**: watchdog rides PL bank-35,
  xdc-sourced. **LAW 0**: PCA9306 isolates the gated bus from always-on I2C.
- ⚠ low review: verify QWIIC J10 pad-1 vs silk before fab (noted in docstring).

- Device id stays **live-sourced** from the SoM project (C3).

## Deferred (big-rocks / risk — better with your review, not done overnight)

Bus notation, per-part rule engine, `place.py` split, BOM+CPL (DS-1), part
lifecycle/EOL snapshot, inline-parts→folders. All tracked with rationale in the
plan.

## How to verify

```
python3 -m schgen board          # 26 sheets, every gate PASS
python3 -m schgen selftest       # 53/53 mutants killed + byte-determinism
python3 -m pytest schgen/tests/  # 154 unit cases
python3 -m schgen thermal        # the Tj gate (the buck review item)
python3 -m schgen design-rules   # the completeness gate
```
