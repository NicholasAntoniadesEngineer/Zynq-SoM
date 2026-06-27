# SOM ↔ Carrier Coordination Audit

> **Run:** 59-agent competitive cross-board coordination pass (`.som_audit_pass4_carrier.js`), 2.47 M tokens. New ground-truth axis: a 3-way pin map (SOM netlist ↔ `som_interface.json` contract ↔ carrier netlist) over all 300 DF40 contacts.
>
> **Orchestrator verification — every CRITICAL/HIGH/MEDIUM below was re-checked by hand against the two netlists (and datasheets) before landing:**
> - **DF40 double-receptacle (CRITICAL):** SOM PCB/BOM = `DF40C-100DS` (C597931); carrier J24001/J25002/J26003 = the *same* `DF40C-100DS` (C597931). Hirose: DS=receptacle, mates only to DP=plug. Two receptacles ⇒ no mate. ✓
> - **+5V_SOM = 4.65 V (HIGH):** carrier `R22014=47.5k` (top) / `R22015=13k` (bottom) on `U22004=LM61460` (Vref 1.0 V) ⇒ 1.0×(1+47.5/13)=**4.654 V**. ✓
> - **FMC_LA08 split (HIGH):** SOM `J1.74=IO_L1_P_35`, `J1.92=IO_L1_N_35` carry carrier `FMC_LA08_P/_N` — 18 contacts apart, same row. ✓
> - **SC-I2C on PA4/PA5 (MEDIUM):** SOM `J1.49/J1.55 = U9(STM32G431).12/.13 = PA4/PA5` — DAC/SPI/UCPD pins, **no I2C alternate function** — carry the carrier's FUSB302+INA3221×2+TCA9535+PCA9306 I2C bus. ✓
> - **Camera D-PHY (CRITICAL/HIGH):** carrier `camera` sheet = J8001 (RPi FFC) + 3×100R + 2×TPD4E02B04 ESD + I2C pulls only — **no D-PHY bridge / XAPP894 network**; Zynq-7020 has no MIPI hard IP. ✓
> - The panel **self-killed 6 false positives** including an *inverted* PUDC_B claim (R7009 is on GND, strap is LOW = correct) and two wrong diff-pair splits (LA09/LA06-07 are adjacent) — recorded under "Rejected candidates" so they're not re-raised.
>
> **This OVERTURNS the SOM-internal audit's DF40 assumption** that "the carrier provides the mating DP plug." It does not — both boards are DS. The consolidated SOM report has been updated to point here.

# SOM <-> Carrier Coordination Audit

## Executive summary

**Can the assembled stack work as drawn? No.** There is one hardware-fatal, board-dead discoordination at the mechanical interface that prevents the SoM from ever seating on the carrier, plus a non-functional camera subsystem and several supply/signal-integrity faults that would compromise the stack even if the boards could mate.

Confirmed discoordinations by severity (de-duplicated by root cause; the JSON's two DF40 entries are one fault, and its three camera entries are one fault):

| Severity | Count | Items |
|---|---|---|
| CRITICAL | 2 | DF40 double-receptacle no-mate; MIPI CSI-2 camera with no D-PHY front end |
| HIGH | 3 | +5V_SOM buck set to 4.65 V; +5V_SOM inductor under-rated for SoM draw; FMC_LA08 split across non-adjacent DF40 contacts |
| MEDIUM | 1 | SC I2C bus landed on STM32 PA4/PA5 (no hardware I2C) |
| LOW | 1 | PS-JTAG TCK has no pull-up on either board |

**The single most important item:** the DF40 gender clash (panel 3/3, confidence 0.97). The SoM and the carrier *both* instantiate the **DF40C-100DS-0.4V(51) receptacle** (LCSC C597931) on all three board-to-board connectors. DF40 mates only as plug (DP) to receptacle (DS); two receptacles have no interlocking contact geometry, so the assembled stack has zero electrical connection across all 300 pins and zero mechanical retention. This passes every existing gate (netlist 0/300, GND 0/300, ERC/DRC clean) because connector gender is a physical-part attribute none of those checks inspect. It also overturns the SoM-internal audit's assumption (SOM_ELECTRICAL_AUDIT.md lines 112/114) that "the carrier provides the mating DP plug" — this cross-board check proves that assumption FALSE and closes that TODO.

**Verified positives (the coordination that IS correct):**
- **Contract fidelity:** the carrier connector contract matches the SoM netlist **0/300** — every logical pin agrees.
- **Pin map is NOT mirrored:** the pin mapping is straight-through, not flipped; this is a real, verified positive, not an assumption.
- **GND alignment 0/300:** all ground contacts align pin-for-pin across the interface.
- **Power entry coordinated:** carrier VIN <- +5V_SOM feeds the SoM VIN domain as intended; SoM-sourced +3V3/+1V8 are intentionally NC on the carrier per the carrier README.

In short: the *logical* contract between the two boards is essentially perfect, and several earlier suspected faults were refuted (see Rejected candidates). The failures are concentrated in **physical-part selection** (connector gender, inductor rating, FB divider) and **delegated analog front-ends** (MIPI D-PHY, SC-I2C peripheral mapping) — exactly the classes of fault that netlist/ERC/DRC gates cannot see.

---

## CRITICAL & HIGH discoordinations

### CRITICAL-1 — DF40 double-receptacle: boards cannot mate (panel 3/3, conf 0.97)

- **What / where:** Both projects place the identical Hirose **DF40C-100DS-0.4V(51)** receptacle (LCSC **C597931**) on every board-to-board connector. SoM: J1, J2, J3 (PCB `Zynq_SoM.kicad_pcb`, fp `HRS_DF40C-100DS-0.4V_51_` on B.Cu at lines 58383/94171/80630; Value `DF40C-100DS-0.4V_51`). Carrier: J24001, J25002, J26003 (`som_j1/j2/j3.kicad_sch`, Footprint `DF40C-100DS-0.4V_51:DF40C-100DS-0.4V_51`, Value `DF40C-100DS-0.4V(51)`, LCSC C597931). Affects all 300 interface pins.
- **Why (datasheet):** Hirose DF40 (hirose.com / Farnell) mates as DS (receptacle/socket) ↔ DP (plug). A link needs exactly one DS and one DP at matched stack height. The two lands are physically different: **DS rows at Y=±1.54 mm (3.08 mm spacing, 100 pads); DP rows at Y=±1.355 mm (2.71 mm spacing, 104 pads incl. hold-downs)** — not interchangeable by rename.
- **Impact on the assembled stack:** Hardware-fatal. Two receptacles do not interlock — zero electrical connection on all 300 pins, zero mechanical retention. The SoM cannot be seated. Invisible to netlist (0/300), GND (0/300), ERC, DRC because gender is not modeled there. Overturns the SoM audit's MEDIUM-only demotion (SOM_ELECTRICAL_AUDIT.md L112/L114).
- **Fix:** Make exactly ONE board the DP plug; keep the other DS. Convention + evidence favor changing the **carrier** (host) to DP on J24001/J25002/J26003: Value -> `DF40C-100DP-0.4V(51)`, footprint -> the DP land (rows ±1.355 mm, 104 pads), LCSC -> the DF40C-100DP-0.4V(51) plug, and order the plug. Stack height already coordinated (both `(51)` = 1.5 mm), so order a 1.5 mm DP. Re-verify pin-1 land alignment after the swap (DP pad-1 at X=−9.8 vs DS pad-1 at X=+9.8 — orient the DP footprint so logical pin N still seats on pin N when the boards face each other). Separately, correct the SoM *schematic* symbol's footprint field (currently DP) back to DS per the SoM audit so "Update PCB from schematic" does not re-corrupt the fabricated DS land.
- **Panel vote:** 3/3.

### CRITICAL-2 — MIPI CSI-2 camera wired into Zynq HR I/O with no D-PHY front end (panel 3/3, conf 0.72–0.82)

- **What / where:** Carrier sheet `camera.kicad_sch`, titled "RPi camera port: 2-lane MIPI CSI-2 (15P FFC)". J8001 (SFW15R-1STE1LF). The three D-PHY pairs route J8001 -> 100R series (R8001/R8002/R8003) -> TPD4E02B04 ESD (U8001/U8002) -> straight onto SoM J3 / carrier J26003, Zynq-7020 PL bank 35:
  - CAM_D0_P/N = J3.5 / J3.7 (IO_L10_P/N_35)
  - CAM_D1_P/N = J3.17 / J3.15 (IO_L15_DQS_P/N_35)
  - CAM_CLK_P/N = J3.9 / J3.11 (IO_L13_MRCC_P/N_35)
  - +VCCO_35 = +2V5_VADJ (2.5 V) on J3.1/2/4
- **Why (datasheet/UG585/UG933, XAPP894):** The XC7Z020 is a 7-series device with **no MIPI D-PHY hard IP** and only HR (no HP) banks — UG585/UG933 contain no MIPI/D-PHY support. A RPi-class sensor (OV5647/IMX219) drives D-PHY only: HS ≈ 200 mVpp diff at ~200 mV common-mode, plus LP single-ended 0–1.2 V. Receiving D-PHY on 7-series HR I/O requires either a dedicated CSI-2 bridge/deserializer OR the XAPP894 sub-LVDS resistor network (per-lane bias/clamp/termination handling BOTH HS and the LP-11 stop state / lane init / escape) with the bank at the right I/O standard. The carrier provides ONLY a single differential 100R termination + ESD per lane — that handles HS swing only and leaves LP mode entirely unhandled; nothing senses LP single-ended levels, which gate every CSI-2 transaction. (Note: the 2.5 V VCCO_35 itself is NOT the fault — 2.5 V is correct for the FMC LVDS_25 breakout, the RTL8211F open-drain INT pull-up, and an HS-mode LVDS_25 receiver. The fault is the absent D-PHY adaptation, not a VCCO mismatch.)
- **Impact on the assembled stack:** The camera subsystem is non-functional as drawn. Without the LP receive path/level translation the Zynq cannot detect LP-11 -> HS entry, so the CSI-2 link never starts; no usable pixel data. LP ~1.2 V also sits on a 2.5 V bank with only a clamp diode. Passes ERC/DRC/netlist because every lane terminates to a valid GND-flanked pair on a powered bank. This is a coordination fault: the carrier delegates a D-PHY-to-FPGA front-end that exists on neither board.
- **Fix:** Add the missing front-end on the carrier: either (a) the per-lane XAPP894 D-PHY-to-LVDS resistor network (series + bias/clamp per data and clock lane) with the pins configured LVDS_25 (HS) / LVCMOS or HSUL_12 (LP), or (b) a dedicated MIPI CSI-2 receiver/deserializer bridge ahead of the SoM, or (c) re-spec the port to a genuine parallel/sub-LVDS-at-2.5 V sensor. Document the chosen CSI-2 receive method and required bank-35 VCCO as a binding carrier requirement in the SoM integration guide / `som_interface.json`. Because bank 35 is shared with the FMC LA pairs, any change must keep camera and FMC I/O standards compatible on one VCCO.
- **Panel vote:** 3/3.

### HIGH-1 — +5V_SOM buck FB divider sets 4.65 V, not 5 V (panel 3/3, conf 0.85)

- **What / where:** Carrier `power_som`, sheet "Power: +VIN -> +5V_SOM always-on buck". U22004 = TI **LM61460AANRJRR** (C2864505), 1.0 V-reference adjustable buck. FB node `Net-(U22004-FB)` (pin 4): RFBT = R22014 = **47.5k** (pin1 on +5V_SOM), RFBB = R22015 = **13k** (pin2 on GND). Feeds SoM VIN contacts J1.1–14.
- **Why:** Vout = VREF·(1 + RFBT/RFBB) = 1.0·(1 + 47.5/13) = **4.654 V** — ~7% low. A true 5.0 V needs ratio 4.0 (e.g. 47.5k / 11.87k, or 52.3k / 13k). SoM audit documents VIN nominal "4.2–5 V" with 5 V intended and 4.2 V as the LOW corner; on-module regulators U4/U6/U8/U10/U13 are specified against a 5 V input.
- **Impact on the assembled stack:** 4.654 V at the buck output, minus DF40 contact IR drop (VIN is a 14-contact / 0.3 A-per-contact bottleneck) minus copper drop, lands SoM VIN near or below 4.2 V under load. Lower input forces every on-SoM buck to draw MORE input current for the same output power, compounding HIGH-2. Silent to ERC/DRC/netlist (FB value never checked vs rail name).
- **Fix:** Re-target to 5.0 V — keep RFBT = 47.5k, change RFBB 13k -> ~11.8–11.9k (or 52.3k/13k); re-confirm against LM61460 VREF = 1.0 V. Then verify SoM VIN ≥ 4.2 V after DF40 + PCB IR drop at worst-case current.
- **Panel vote:** 3/3.

### HIGH-2 — +5V_SOM output inductor under-rated for SoM worst-case draw (panel 3/3, conf 0.80)

- **What / where:** A single U22004 (LM61460, a 6 A-capable IC) with a single inductor L22003 = Sunlord **SWPA8040S100MT** (10 µH, **3.3 A Irms / ~4.1 A Isat**, DCR ~29–38 mΩ) feeds the entire SoM. Verified no paralleling on +5V_SOM (the other two LM61460s U20001/U20002 are on unrelated rails). SoM loads: U8 (+1V0/4A), U4 (+1V8/3A), U6 (+3V3/3A), U10 (+1V35/2A), U13 (+3V3_SC).
- **Why:** SoM audit tallies worst-case module input ≈ **5.2 A at 5 V** (~23 W / ~88% eff) and **~6.2 A at the 4.2 V low corner**. A 6 A buck feeding ~5 A must have an inductor rated ≥ peak inductor current (load + ½ ripple), i.e. ≥ ~6 A Isat — not 3.3 A Irms / 4.1 A Isat.
- **Impact on the assembled stack:** The stage is hard-limited by L22003 to ~3.3 A continuous (heating) and ~4.1 A (saturation) — below the SoM's potential 5.2 A. Under high simultaneous loading (PL + DDR + GbE + USB) the inductor saturates/overheats, the buck loses regulation (collapsing +5V_SOM, compounding HIGH-1) and the SoM browns out. This is the carrier-SIDE counterpart to the SoM's "14 VIN contacts" finding — adding contacts cannot help while the inductor caps the stage. DRC/ERC/netlist cannot see inductor current rating vs load.
- **Fix:** Replace L22003 with ~10 µH (or 4.7 µH for the LM61460 switching freq) rated ≥ 6 A Isat and ≥ ~5.5 A Irms in an 8×8 (or larger) footprint. Bench-confirm +5V_SOM delivers the SoM's tallied worst-case input current at the 4.2 V low corner with margin; re-check LM61460 thermal/duty at that load.
- **Panel vote:** 3/3.

### HIGH-3 — FMC_LA08 differential pair on non-adjacent DF40 contacts (panel 3/3, conf 0.88)

- **What / where:** Carrier assigns FMC_LA08_P/_N to net class **DP100_DIFF** (100 Ω diff) and routes them adjacent on FMC header J11001 (.29/.30). Through the DF40 they map to SoM J1: FMC_LA08_P -> J24001.74 (SoM IO_L1_P_35), FMC_LA08_N -> J24001.92 (SoM IO_L1_N_35). The two contacts are 18 positions apart in the same DF40 row: **pad-to-pad span 7.2 mm** vs 0.8 mm for a correct delta=2 adjacent pair. The Zynq pins themselves ARE a true L1_35 pair (polarity correct); only the connector-contact assignment is split. N (pin 92) is additionally flanked by GbE aggressor ETH_PHY_MDI1_P (pin 91).
- **Why (UG933):** A _P/_N pair used differentially (FMC LA = LVDS-annex) must be routed tightly coupled and length-matched; the board-to-board transition must keep P and N on adjacent contacts with GND nearby to preserve coupled impedance and intra-pair skew. The carrier's own DP100_DIFF class declares that intent. (The SoM audit already notes some MRCC/SRCC pairs on non-adjacent contacts at LOW; this is elevated because the carrier actively drives LA08 as differential.)
- **Impact on the assembled stack:** P and N traverse different contact regions (7.2 mm apart) — not impedance-controllable or skew-matchable through the mezzanine. Large unbounded intra-pair skew plus crosstalk from interposed GbE/SDIO. Any FMC mezzanine using LA08 as an LVDS pair or diff clock sees degraded eye / failed timing. Single-ended use unaffected.
- **Fix:** On the SoM, reassign IO_L1_P/N_35 to an adjacent same-row DF40 contact pair (delta=2) with GND flanking; OR formally annotate FMC_LA08 as single-ended-only in the pinout and remove it from DP100_DIFF on the carrier. Do not rely on length-matching to fix a 7.2 mm contact split.
- **Panel vote:** 3/3.

---

## MEDIUM / LOW / INFO

### MEDIUM — SC I2C bus landed on STM32 PA4/PA5, which have no hardware I2C (panel 3/3, conf 0.75)

- **What:** Carrier routes its system-controller I2C bus to J1.49 / J1.55, which on the SoM are STM32 U9 (STM32G431CBUx) pins **PA4 / PA5** (named STM32_DAC1 / STM32_DAC2). Five peripherals hang on it with pull-ups R7004/R7005: FUSB302 PD (U30001), 2× INA3221 (U21001/U21002), TCA9535 (U7001), PCA9306 (U1002).
- **Why (STM32G431 AF table):** PA4/PA5 expose SPI1, USART2, TIM3, UCPD1, DAC1_OUT1/OUT2, EVENTOUT — **no I2C alternate function** (AF4 I2C is on PA8/PA9, PB6–9, PC4, PF0/F1, etc.). The STM32's only hardware I2C2 (PA8=STM32_SDA, PA9=STM32_SCL) is already consumed by the SoM-internal Zynq I2C link (MIO14/15) and is NOT brought to the connector.
- **Impact:** USB-PD negotiation, rail-current monitoring, and the bring-up IO-expander all depend on this bus. With no hardware I2C on PA4/PA5 it can only work by firmware GPIO bit-bang (timing-marginal for FUSB302 PD) — or not at all if firmware targeted the HW peripheral. A coordination fault: the carrier assumes I2C-master capability on pins the SoM cannot drive in hardware.
- **Fix:** Re-pin the carrier SC I2C bus to SoM connector pins mapping to a hardware-I2C-capable STM32 pin pair, or bring out spare I2C-capable GPIO. If bit-bang is intended, document it explicitly and confirm FUSB302 PD timing tolerance. Verify against STM32G431 datasheet Table 13.

### LOW — PS-JTAG TCK has no pull-up on either board (panel 3/3, conf 0.70)

- **What:** ZYNQ_TCK (J1.64) reaches the carrier USB-JTAG buffer (SN74LVC125 U28002.1Y) and header J9001.6 with **no pull-up**; the SoM has none either. The carrier DOES pull TMS (R9001 4k7) and TDI (R9002 4k7) to +3V3 — TCK is the omission, contrary to UG933 ("TDI, TMS, and TCK should be pulled up").
- **Impact:** Low. With TMS pulled high the TAP is held toward Test-Logic-Reset, so a floating TCK is largely benign; TCK is actively driven whenever a programmer or the buffer is enabled. Risk limited to noise-induced TCK edges while the bus is idle/undriven. VCCO_MIO0 (Bank 500) is +3V3, so the carrier's 3.3 V buffer/pulls are correctly level-matched (no overvoltage) — purely a missing-pull nit.
- **Fix:** Add a 4k7 pull-up on ZYNQ_TCK to +3V3 on the carrier (mirroring R9001/R9002), or on the SoM for standalone robustness. Confirm the JTAG buffer OE default leaves the bus benign.

### INFO — bank-voltage / delegated-part / firmware items to confirm

- **Bank 35 VCCO = 2.5 V (+2V5_VADJ) is shared** by the FMC LA pairs and the camera lanes, sourced by a FIXED 2.5 V LDO (U11001 TLV75725). 2.5 V is the *correct* level for the FMC LVDS_25 breakout, the RTL8211F open-drain INT pull-up, and an HS-mode LVDS_25 camera RX — so this is NOT a fault (see Rejected candidates), but any camera-front-end redesign (CRITICAL-2) must remain I/O-standard-compatible with the FMC pairs on the single shared VCCO.
- **Firmware handshake (SC I2C):** confirm whether STM32 firmware targets a hardware I2C peripheral or a bit-bang driver — this determines whether MEDIUM is fatal or merely sub-optimal.
- **Delegated parts:** the SoM intentionally delegates PS-JTAG pulls and camera lane termination/level-conditioning to the carrier (SOM_ELECTRICAL_AUDIT.md L313). LOW (TCK) and CRITICAL-2 (D-PHY) are both gaps in that delegation — confirm the delegation contract is documented in the SoM integration guide.

---

## What is correctly coordinated (positive record)

- **Contract fidelity — contract == SoM netlist, 0/300.** The carrier connector contract agrees with the SoM netlist on every one of the 300 interface pins. The logical interface is faithful.
- **Pin map NOT mirrored.** The mapping is straight-through; there is no row-flip / pin-1 mirror error. Verified, not assumed.
- **GND alignment 0/300.** Every ground contact aligns across the interface.
- **Power entry coordinated.** Carrier VIN <- +5V_SOM correctly feeds the SoM VIN domain (the *value* of that rail is a separate HIGH; the *routing/intent* is correct).
- **SoM-sourced rails correctly NC.** SoM-sourced +3V3 / +1V8 are intentionally left NC on the carrier per the carrier README — a deliberate, documented decision, not a missing connection.
- **JTAG domain level-match.** Carrier 3.3 V JTAG buffer and TMS/TDI pulls correctly target the SoM's +3V3 VCCO_MIO0 domain (no overvoltage).

The net picture: the *logical* SoM↔carrier contract is essentially flawless. Every confirmed fault is a physical-part or analog-front-end issue that the logical gates cannot detect.

---

## Rejected candidates (panel-killed)

These were investigated and **refuted** — recorded so they are not re-raised:

1. **Bank 35 VCCO=2.5V "hard-locked, no independent VADJ adjust" (LOW, 1/3).** Factual setup reproduced (VCCO_35 = +2V5_VADJ from fixed-2.5 V LDO U11001; bank carries both FMC LA pairs and camera lanes), but 2.5 V is the *correct/required* level for all three bank-35 consumers (FMC LVDS_25, RTL8211F open-drain INT pull-up, HS-mode LVDS_25 camera RX). Not a discoordination.
2. **FMC_LA09 P/N on non-adjacent DF40 contacts (HIGH, 0/3).** REFUTED. Pin map SoM==CONTRACT==CARRIER pin-for-pin; the authoritative footprint geometry (`parts/DF40C-100DS-0.4V_51/…kicad_mod`) shows pins 51–100 form one row, and LA09_P=J1.80 / LA09_N=J1.84 are a correctly-adjacent same-row pair. The 7.2 mm split is real only for LA08 (HIGH-3), not LA09.
3. **FMC_LA06/LA07 straddling two DF40 rows (3.22 mm) (MEDIUM, 0/3).** REFUTED. Premise (a "block-of-50" row layout) is false; actual pad geometry from the released footprint disproves the cross-row split.
4. **Carrier drives PUDC_B strap HIGH (pull-ups disabled) (MEDIUM, 0/3).** REFUTED — inverted. R7009 pin 1 is on **GND**, not +1V8 (carrier netlist), so the strap is pulled LOW, matching the SoM's delegated safe default.
5. **Dual USB-PD CC controllers on one CC pair: STM32 UCPD vs carrier FUSB302 (HIGH, 1/3).** Only 1/3 panel confirmation; not landed as a confirmed coordination defect in this report. (STM32_USB_CC1/CC2 = U9.44/PB6, U9.42/PB4, shared to carrier nets — flagged for re-confirmation, but did not reach panel majority.)
6. **Carrier TMS/TDI pull to +1V8 vs SoM 3.3 V PS-JTAG (HIGH, 0/3).** REFUTED. R9001 and R9002 both pull to **+3V3** (carrier netlist) — no domain mismatch. The only real JTAG nit is the missing TCK pull (LOW above).

---

Source artifacts referenced: `som/SOM_ELECTRICAL_AUDIT.md`; SoM PCB `/Users/nicholasantoniades/Documents/GitHub/Zynq-SoM/som/Zynq_SoM.kicad_pcb`; SoM footprint `/Users/nicholasantoniades/Documents/GitHub/Zynq-SoM/parts/DF40C-100DS-0.4V_51/DF40C-100DS-0.4V_51.kicad_mod`; carrier schematics `som_j1/j2/j3.kicad_sch`, `camera.kicad_sch`, `power_som`; carrier netlist artifacts under `/tmp/`.