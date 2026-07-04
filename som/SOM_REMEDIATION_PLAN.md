# Zynq-7020 SoM + Carrier — Master Remediation Plan

**Single, definitive list of all work required to make the SoM electrically correct and able to work with its carrier.**
Plan only — no design files have been modified. Every item was found across five adversarial audit passes (~280 agents) and each fix was independently design-verified (correct / complete / introduces-no-new-bug). Evidence: `SOM_ELECTRICAL_AUDIT.md`, `SOM_CARRIER_COORDINATION.md`, `SOM_INTERFACE_WIRING_AUDIT.md`.

Targets: SoM `som/` (XC7Z020-CLG484) · carrier `carrier/` · interface contract `carrier/som_interface.json`.

---

## 0. Status & master checklist

**Do not fabricate the SoM until the four CRITICALs (S1, S2, I1, C1) are applied and re-verified.** The logical SoM↔carrier contract is otherwise sound (pin map 0/300 mismatches, GND aligned, all high-speed buses verified clean).

| ID | Board | Sev | Item | Effort | Verified |
|----|-------|-----|------|--------|----------|
| **S1** | SoM | 🔴 CRIT | DDR DCI VRP/VRN on wrong rails (R46/R47) | schematic + minor layout | ✅ (rails); ⚠️ value contingent |
| **S2** | SoM | 🔴 CRIT | DDR3L x16 on wrong Zynq byte lanes (DQ[31:16]) | **layout-major** | ✅ mapping exact |
| **I1** | Interface | 🔴 CRIT | DF40 gender — SoM schematic still DP | schematic only | ✅ carrier DP already done |
| **C1** | Carrier | 🔴 CRIT | MIPI camera has no D-PHY front-end | schematic + layout (+fw) | ⚠️ needs path decision |
| **S6** | SoM | 🟠 HIGH | Boot straps MIO4/MIO5 float at POR | schematic only | ✅ |
| **S4** | SoM | 🟠 HIGH | RTL8211F 25 MHz clock at 1.8 Vpp (needs 3.3) | schematic only | ✅ |
| **S3** | SoM | 🟠 HIGH | eMMC U7 BOM identity (LCSC≠MPN) | schematic/BOM only | ✅ (corrected) |
| **C2** | Carrier | 🟠 HIGH | +5V_SOM buck set to 4.65 V | schematic only | ✅ |
| **C3** | Carrier | 🟠 HIGH | +5V_SOM inductor under-rated | part change | ✅ |
| **I2** | Interface | 🟠 HIGH | FMC_LA08 diff pair split across contacts | schematic + minor layout | ✅ |
| **S7** | SoM | 🟡 MED | PL DONE has no pull-up | schematic only | ✅ |
| **C4** | Carrier | 🟡 MED | SC-I2C on STM32 PA4/PA5 (no HW I2C) | schematic + layout | ✅ |
| **S5** | SoM | 🟡 MED | Source-of-truth & BOM hygiene (R80/R81, DF40 field, LCSC, BMI323 C14) | schematic/BOM only | ✅ (corrected) |
| **C5** | Carrier | 🟢 LOW | PS-JTAG TCK has no pull-up | schematic only | ✅ |

---

## A. SoM board changes

### A.1 · S1 — DDR3L DCI VRP/VRN rail swap (+ value) — 🔴 CRITICAL
File: `som/schematic/DDR3L.kicad_sch`. Root cause: DCI reference resistors on inverted rails; UG585/UG933 require **VRP→GND, VRN→VCCO_DDR(+1V35)**.

| Ref / net | BEFORE | AFTER |
|---|---|---|
| R47 free end (VRP; pin2→U2.N7 stays) | R47.1 → **+1V35** | R47.1 → **GND** |
| R46 free end (VRN; pin1→U2.M7 stays) | R46.2 → **GND** | R46.2 → **+1V35** |
| R46/R47 value | 100 R (C270336) | **80.6 Ω 1%** *(only if 40 Ω DDR trace target)* |

- **Rail swap is unconditional.** Value change is **contingent** on the board's DDR single-ended trace impedance: 40 Ω → 80 Ω (UG933 Table 5-2 DDR3L); if the design is 50 Ω, keep 100 R and change rails only. **Decide from the stackup before touching the value.** Verify any 80.6 Ω LCSC on lcsc.com (proposed `C473438` was not independently confirmable).
- Implement as a true net reassignment (move wire/label endpoints), not a label rename.
- **Verify:** netlist shows `DDR_VRP={R47.2,U2.N7}` with R47.1 on GND; `DDR_VRN={R46.1,U2.M7}` with R46.2 on +1V35. Bring-up: PS DDR DCI calibration completes (no cal-timeout).

### A.2 · S2 — DDR3L x16 re-route from dead upper lanes → active lower lanes — 🔴 CRITICAL
File: `som/schematic/DDR3L.kicad_sch` (SoM-internal U1↔U2 only — touches **no** DF40/carrier pins). Root cause: the 16-bit data bus must be on Zynq DQ[15:0]/DQS0,1/DM0,1 (UG585 DDRIOB_DATA0); it is wired to DQ[31:16]/DQS2,3/DM2,3 (never driven for data). Re-net all 22 signals; each DRAM byte moves as a unit.

**DRAM byte 0 (DQ0-7/LDQS/LDM) → Zynq data slice 0:**

| Net | U1 pin | BEFORE (U2) | AFTER (U2) |
|---|---|---|---|
| DDR_DQ0 | E3 | U1 (DQ25) | **D1** |
| DDR_DQ1 | F7 | AA1 (DQ26) | **C3** |
| DDR_DQ2 | F2 | U2 (DQ27) | **B2** |
| DDR_DQ3 | F8 | Y3 (DQ29) | **D3** |
| DDR_DQ4 | H3 | W3 (DQ30) | **E3** |
| DDR_DQ5 | H8 | AA3 (DQ24) | **E1** |
| DDR_DQ6 | G2 | W1 (DQ28) | **F2** |
| DDR_DQ7 | H7 | Y1 (DQ31) | **F1** |
| DDR_DQS0_P | F3 | V2 (DQS_P3) | **C2** |
| DDR_DQS0_N | G3 | W2 (DQS_N3) | **D2** |
| DDR_DM0 | E7 | AA2 (DM3) | **B1** |

**DRAM byte 1 (DQ8-15/UDQS/UDM) → Zynq data slice 1:**

| Net | U1 pin | BEFORE (U2) | AFTER (U2) |
|---|---|---|---|
| DDR_DQ8 | D7 | R3 (DQ20) | **G2** |
| DDR_DQ9 | C3 | N3 (DQ18) | **G1** |
| DDR_DQ10 | C8 | T2 (DQ21) | **L1** |
| DDR_DQ11 | C2 | M2 (DQ22) | **L2** |
| DDR_DQ12 | A7 | R1 (DQ23) | **L3** |
| DDR_DQ13 | A2 | M1 (DQ16) | **K1** |
| DDR_DQ14 | B8 | T1 (DQ19) | **J1** |
| DDR_DQ15 | A3 | T3 (DQ17) | **K3** |
| DDR_DQS1_P | C7 | N2 (DQS_P2) | **H2** |
| DDR_DQS1_N | B7 | P2 (DQS_N2) | **J2** |
| DDR_DM1 | D3 | P1 (DM2) | **H3** |

- Relabel all 22 wire/hier-labels `PS_DDR_*_16..31 / DQS2,3 / DM2,3` → `..._0..15 / DQS0,1 / DM0,1`. The 22 freed upper-lane balls revert to NC: M1, M2, N2, N3, P1, P2, R1, R3, T1, T2, T3, U1, U2, V2, W1, W2, W3, Y1, Y3, AA1, AA2, AA3.
- **Layout:** full bank-502 escape re-route. DQ bits **within** a lane may be swizzled freely to ease routing; **DQS pairs and DM are pinned** (do not swizzle). Length-match DQ0-7+DM0 to DQS0, DQ8-15+DM1 to DQS1.
- **Firmware:** none (Vivado PS DDR already assumes 16-bit DQ[15:0]; confirm "no ECC / 16-bit").
- **Verify:** netlist — every DDR_DQ0..15/DQS0,1/DM0,1 on slices 0/1; **zero `PS_DDR_*_2/_3` on any DRAM net**. Bring-up: per-byte-lane write-leveling + read training, then walking-1/0 + address-march memtest.

### A.3 · S6 — Boot-mode straps MIO4/MIO5 have no fixed POR default — 🟠 HIGH
File: `som/schematic/zynq_config.kicad_sch` (boot straps). Root cause: MIO4 (`QSPI_D2/BM2`) and MIO5 (`QSPI_D3/BM0`) are biased only through 10k series (R1/R6) to STM32 PA7/PB2; `PS_POR_B` is pulled to +3V3 by R100 and releases independent of the STM32, so a cold boot can sample floating boot bits → undefined boot device.

- **Add** a weak strap to default to Quad-SPI boot ({MIO5,MIO4,MIO3}={1,0,0}): **MIO4 (QSPI_D2/BM2) → ~20k pull-DOWN to GND**; **MIO5 (QSPI_D3/BM0) → ~20k pull-UP to +3V3 (VCCO_MIO0)**. Keep R1/R6 series so the STM32 can still override at runtime. (MIO2/MIO3 are already statically strapped via R76/R77→GND.)
- **Verify:** netlist shows the new pulls on MIO4/MIO5; DC level at MIO4=0, MIO5=1 with STM32 GPIOs Hi-Z. Bring-up: cold power-cycle boots from QSPI every time with the STM32 held in reset.

### A.4 · S4 — RTL8211F 25 MHz oscillator rail 1V8→3V3 + assign X2 part — 🟠 HIGH
File: `som/schematic/Ethernet PHY.kicad_sch`. Root cause: X2 powered from +1V8 → ~1.8 Vpp into U3.37 EXT_CLK, which needs **3.15–3.45 Vpp** (RTL8211F Table 55). (During analysis an agent auto-applied the rail move; it has been **reverted**, so both sub-steps below are TO-DO.)

| Item | BEFORE | AFTER |
|---|---|---|
| Osc-supply rail (L6.2 source / label) | +1V8 / `25MHz_1V8` | **+3V3 / `25MHz_3V3`** |
| X2 part (Value / MPN / LCSC) | `ASE-xxxMHz` / — / blank | **`25.000MHz` / `OT201625MJBA4SL` / `C669080`** (YXC, 1.8–3.3 V, 2016-4P, ±50 ppm) |

- Keep R20 (22R series) and U3.36 XTAL_IN→GND. Do **not** touch USB X1 (1.8 V is correct for the USB3318 digital REFCLK).
- **Separate pre-existing task** (don't bundle): `#PWR023` on this sheet has `lib_id power:+1V8` but `Value "+3V3"` — a mislabeled symbol; fix independently.
- **Verify:** osc net resolves to +3V3 (zero +1V8 members); X1 stays +1V8. Bench: U3.37 = 3.15–3.45 Vpp at 25 MHz.

### A.5 · S3 — eMMC U7 BOM identity lock — 🟠 HIGH
Files: `som/manufacturing/assembly/BOM.csv` (line 39), `som/schematic/emmc.kicad_sch`. Root cause: Value/MPN = ISSI IS21ES08G but LCSC `C499918` = Samsung KLM8G1GETF-B041 (the part actually placed). **Lock to the placed part — identity relabel only:**

| Field | BEFORE | AFTER |
|---|---|---|
| BOM Value/Comment | IS21ES08G | **KLM8G1GETF-B041** |
| BOM MPN | IS21ES08GA-JCLI-TR | **KLM8G1GETF-B041** |
| BOM LCSC | C499918 | **C499918 (no change)** |
| Footprint | BGA153 | **no change** (JEDEC-153, correct) |
| `emmc.kicad_sch` U7 Value ×6 | IS21ES08G | **KLM8G1GETF-B041** |

- **Do NOT** disconnect U7 ball C1 from `eMMC_VDDI` (a verifier-rejected proposal — C1 is an internally-unbonded JEDEC NC; the tie is inert and legal; floating it risks an ERC error). Leave `eMMC_VDDI={C40.1,U7.C1,U7.C2}` and C40 (4u7) as drawn.
- **Verify:** BOM line 39 Value=MPN=KLM8G1GETF-B041 / LCSC C499918 all name one device; ERC=0.

### A.6 · S7 — PL DONE has no pull-up — 🟡 MEDIUM
File: `som/schematic/zynq_config.kicad_sch`. Root cause: `ZYNQ_PL_DONE` (U2.T12, Q3 gate, TP3) has no pull-up; UG585 Table 6-21 requires an external pull-up to VCCO_0 — without it the Q3 DONE-indicator/LED and any DONE sensing can't read high after config.
- **Add** pull-up `ZYNQ_PL_DONE → +3V3` (VCCO_0): 330k per UG585; 4.7k–10k also acceptable.
- **Verify:** netlist shows the pull-up; DONE reads high after configuration (LED via Q3 lights).

### A.7 · S5 — Source-of-truth & BOM hygiene — 🟡 MEDIUM
| Location | BEFORE | AFTER |
|---|---|---|
| `Power.kicad_sch` R80 / R81 Value | 5k1 / 12k | **100k / 100k** (match PCB+BOM; 1V8-sense ÷2 = 0.9 V) |
| R80 / R81 LCSC | gia / gia | **C60491** (100k 1%) |
| `connectors.kicad_sch` J1/J2/J3 footprint+lib_id+Value+MP+LCSC | `…DF40C-100DP…` / `-` | **`…DF40C-100DS…` / `C597931`** (SoM-schematic side of the gender fix — see I1) |
| `Sensors.kicad_sch` C21 LCSC | gia | **C1525** (100n) |
| `Sensors.kicad_sch` C14 (BMI323 VDDIO bypass) | DNP | **populate**, LCSC **C1525**; add to BOM/CPL (100n group qty +1) |
| All `*.kicad_sch` `LCSC Part` containing `gia` (~55) | `gia` / `Cxxxx/gia` | **clean BOM code** — per-value, BOM-driven; **exclude base64 image blobs**; protect C597931, C5368700 |
| `carrier/som_interface.json` lines 4/110/216 footprint | `…DF40C-100DP…` | **`…DF40C-100DS…`** (value already DS) |

- **Verify:** "Update PCB from schematic" → no footprint change on J1/J2/J3 (schematic now matches the fabricated DS land); `grep -c gia schematic/*.kicad_sch == 0` outside base64; ERC=0.
- **Open:** confirm C14 VDDIO bypass wasn't intentionally omitted (datasheet recommends one; populating is the safe call).

---

## B. Carrier board changes

### B.1 · C1 — MIPI CSI-2 camera D-PHY front-end — 🔴 CRITICAL
File: `carrier/schematic/camera.kicad_sch` (+ PL `.xdc` + firmware for Path B). Root cause: the RPi MIPI camera's D-PHY lanes go straight into Zynq-7020 bank-35 with only 3×100R + ESD; the XC7Z020 has no MIPI hard IP and there is no LP-mode receive path → the CSI-2 link can't init. **The "LVDS_25 on the 2.5 V bank" idea was verifier-rejected** (LVCMOS25 VIH 1.7 V can't resolve a 1.2 V LP-high). **Choose ONE path before carrier layout (engineering-management decision):**

- **Path A (recommended) — MIPI-to-parallel/CSI bridge IC.** Add a MIPI CSI-2 RX→parallel/LVDS bridge so the Zynq sees a standard parallel bus; removes the soft-D-PHY firmware burden and the bank-voltage conflict. **Verify an in-stock bridge LCSC via the JLCPCB/LCSC API before BOM commit — do not guess a code.**
- **Path B — XAPP894 soft D-PHY in PL.** Move the 3 camera pairs off bank-35 (locked to 2.5 V by FMC) onto a PL bank settable to **1.8 V** with a free MRCC for CAM_CLK; add the XAPP894 HS sub-LVDS network (series + 100R shunt, external term, `DIFF_TERM FALSE`) and an LP receive path on **1.8 V single-ended** pins (not 2.5 V, not a series-isolation resistor); keep TPD4E02B04 ESD. Firmware: ISERDESE2 1:8 + MMCM + LP state machine + CSI-2 RX-DPHY decoder. Confirm sensor HS rate ≤ ~950 Mb/s/lane (Zynq-7020 PL LVDS limit).
- Unchanged either way: CCI/I2C (CAM_SCL/SDA 4k7→+3V3_CAM), CAM_EN/PWR load switch.
- **Highest residual-risk item; treat as the long pole for carrier video.**

### B.2 · C2 — +5V_SOM buck output 4.65 V → 5.0 V — 🟠 HIGH
File: `carrier/schematic/power_som.kicad_sch`. U22004 = LM61460 (Vref 1.0 V), FB R22014=47.5k (top) / R22015=13k (bottom) → 4.654 V.
- **Change R22015 13k → ~11.8 kΩ** (E96 11.8k → 1.0×(1+47.5/11.8)=5.03 V; or 47.5k/11.9k=5.0 V). Keep R22014=47.5k.
- **Verify:** computed Vout 4.95–5.05 V; confirm SoM VIN ≥ 4.2 V after DF40 IR drop at worst-case current.

### B.3 · C3 — +5V_SOM output inductor under-rated — 🟠 HIGH
File: `carrier/schematic/power_som.kicad_sch`. L22003 = SWPA8040S100MT (10 µH, 3.3 A Irms / 4.1 A Isat) vs SoM worst-case ~5.2 A input.
- **Replace** with ~4.7–10 µH (per LM61460 fsw) rated **≥6 A Isat, ≥5.5 A Irms**, ≥8×8 mm; pick a real in-stock part + LCSC and confirm DCR + LM61460 thermal at load.
- **Verify:** bench — +5V_SOM holds 5 V at the SoM's tallied worst-case current at the 4.2 V input corner; inductor temp in spec.

### B.4 · C4 — SC-I2C bus on STM32 PA4/PA5 (no hardware I2C) — 🟡 MEDIUM
Files: `carrier` SC-I2C sheet(s). The FUSB302 PD + 2×INA3221 + TCA9535 + PCA9306 bus lands on SoM J1.49/J1.55 = STM32 PA4/PA5, which have no I2C alternate function.
- **Re-pin** the carrier SC-I2C to SoM connector contacts that map to a hardware-I2C-capable STM32 pin pair (requires exposing I2C1/I2C2 pins at the connector — coordinate with a SoM-side pin assignment), **or** formally adopt firmware bit-bang and document FUSB302 PD timing tolerance. Decide and cite the STM32G431 AF table.
- **Verify:** chosen pins support hardware I2C (datasheet), or a bit-bang note is recorded with timing analysis.

### B.5 · C5 — PS-JTAG TCK has no pull-up — 🟢 LOW
File: `carrier` JTAG sheet. Carrier pulls TMS (R9001) and TDI (R9002) 4k7→+3V3 but omits TCK.
- **Add** 4k7 pull-up on `ZYNQ_TCK → +3V3` (mirror R9001/R9002; VCCO_MIO0 = +3V3, domain-matched).

---

## C. Interface / DF40 mating changes

### C.1 · I1 — DF40 gender: carrier DP plug + SoM DS receptacle — 🔴 CRITICAL
**Decision (final): carrier = DP plug (C531031); SoM = DS receptacle (C597931), at matched (51)=1.5 mm height.**
- **Carrier side is DONE** — committed as `41c7093` (J24001/J25002/J26003 → DP/C531031), verified in the carrier netlist. **Do not revert.**
- **SoM side = schematic only** (the SoM PCB is already the correct DS land — do **not** touch the SoM PCB). In `som/schematic/connectors.kicad_sch`, change the J1/J2/J3 symbol/lib_id/footprint/Value/MP fields `DF40C-100DP…` → `DF40C-100DS…`, and set the `LCSC Part` property (currently `-`) to **C597931**. Also fix `carrier/som_interface.json` footprint DP→DS (lines 4/110/216) — apply once, shared with S5/I2.
- Pin-1 mating is verified correct (the X-axis mirror of flipping the boards face-to-face seats logical pin N on pin N for all 100 contacts) — no net reassignment.
- **Separate pre-existing task:** the schematic footprint nickname `Mylibrary:` is not in `som/fp-lib-table` (only `fp:`) — fix independently so "Update PCB from schematic" resolves.
- **Verify:** zero `DF40C-100DP` in `connectors.kicad_sch` (except harmless URL text); "Update PCB from schematic" = no footprint change on J1/J2/J3; BOM SoM=C597931 / carrier=C531031.

### C.2 · I2 — FMC_LA08 differential pair split — 🟠 HIGH
SoM `connectors.kicad_sch` + carrier `fmc.kicad_sch` + `som_interface.json`. LA08_N/P are 18 contacts apart; make them in-row adjacent (Δ2) via a symmetric GND swap (boards stay pin-for-pin identical):

| Side | Net | BEFORE | AFTER |
|---|---|---|---|
| SoM J1 | IO_L1_N_35 | J1.92 | **J1.72** |
| SoM J1 (reciprocal) | GND | J1.72 | **J1.92** |
| Carrier J24001 | FMC_LA08_N | .92 | **.72** |
| Carrier J24001 (reciprocal) | GND | .72 | **.92** |
| `som_interface.json` | `"72":GND,"92":IO_L1_N_35` | — | **`"72":IO_L1_N_35,"92":GND`** |

- IO_L1_P_35 stays on contact 74 (polarity preserved); GND count stays 20/connector. This is a **pin-to-net reassociation** in KiCad, not a label retype.
- **Cheaper alternative (Option B):** if no carrier will ever route LA08 differentially, just remove LA08 from the carrier's diff/impedance class — zero PCB rework. (Benefit of the swap is limited to the SoM-internal segment + future diff-capable carriers; the carrier endpoint is a 2.54 mm header.)
- **Verify:** `IO_L1_N_35={J1.72}`; `FMC_LA08_N={J24001.72,J11001.30}`; pads 72/74 same row Δ2.

---

## D. Apply order & cross-fix dependencies

1. **S1 + S2 — one combined DDR layout pass** (both hit the bank-502 region; do the S1 stub re-via and the S2 escape re-route together to avoid two spins).
2. **I1 + S5(DF40 field) + I2 — one DF40 hygiene pass.** All three edit `connectors.kicad_sch` and the same `som_interface.json` lines — apply the JSON edits **once** (DP→DS on 4/110/216; LA08 swap on 72/92). Gate: a single "Update PCB from schematic" = no-op on J1/J2/J3.
3. **S4** (X2 rail + part) — independent; track the `#PWR023` mislabel separately.
4. **S3** (eMMC identity), **S6/S7** (straps, DONE pull-up) — independent schematic/BOM.
5. **S5 remainder** (R80/R81, C14, "gia" sweep) — run the **"gia" sweep LAST**, per-value/BOM-driven, base64-excluded, so it doesn't clobber codes set by S1/S3/S4/I1.
6. **Carrier C2/C3/C4/C5** — independent of SoM edits. **C1** — pick Path A vs B **before** carrier layout; firmware (Path B) parallels layout.

**Shared-file watch:** `connectors.kicad_sch` and `som_interface.json` are each touched by I1 + S5 + I2 — coordinate as one edit. DDR layout region touched by S1 + S2.

---

## E. Re-verify gates (run after changes, before fab)

- **DDR (S1+S2):** netlist — VRP/VRN rails correct; all DQ0-15/DQS0,1/DM0,1 on slices 0/1; zero `PS_DDR_*_2/_3` on DRAM nets; 22 upper balls NC.
- **DF40 (I1):** "Update PCB from schematic" = no footprint change on SoM J1/J2/J3; 300 contacts map identically; BOM SoM=C597931 / carrier=C531031.
- **Ethernet (S4):** osc net = +3V3 only; X1 stays +1V8.
- **Contract:** `som_interface.json` consistent with both schematics (footprint DS, LA08 on 72).
- **Whole-board:** ERC=0; KiCad netlist-equivalence; SHORT/OPEN connected-components check; carrier DRC=0.
- **Bring-up:** DDR memtest + DCI cal DONE + per-byte training; RTL8211F EXT_CLK 3.15–3.45 Vpp; cold-boot from QSPI deterministic; PL DONE reads high; camera LP→HS entry + MMCM lock.

---

## F. Open decisions & caveats (need a human call)

1. **DDR trace impedance (gates S1 value):** 40 Ω → 80.6 Ω; 50 Ω → keep 100 R. Confirm from the stackup. Verify the 80.6 Ω LCSC on lcsc.com.
2. **Camera path (C1):** bridge IC (Path A, recommended) vs soft-D-PHY-in-PL (Path B, firmware-heavy + timing risk). Management decision; long-pole for carrier video.
3. **S2 DQ-bit swizzle within lanes:** layout owner's choice (DDR3 allows it); DQS/DM stay pinned.
4. **C4 I2C:** re-pin to HW-I2C (needs a SoM connector pin exposed) vs documented bit-bang.
5. **I2 LA08:** do the adjacency swap vs declare single-ended (Option B).
6. Pre-existing items to fix as separate tasks (not regressions, not blockers): `#PWR023` mislabel, `Mylibrary:`→`fp:` lib-table nickname, the C14 `+VCCO_33` power-symbol-override construct.

---

*Plan compiled 2026-06-20. Design files unmodified. Apply nothing until S1/S2/I1/C1 are resolved and the §E gates pass.*
