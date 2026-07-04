# SOM Interface & Wiring Audit

> **Run:** 65-agent adversarial interface-by-interface verification (`.som_interfaces.js`), 2.58 M tokens — every Zynq↔peripheral bus traced at the pin / bit-order / direction / protocol level vs UG585 + device datasheets.
>
> **Orchestrator reconciliation (checked vs netlist + prior passes — read this first):**
> - ✅ **All high-speed data buses CLEAN** (verified): DDR addr/cmd/ctrl/clk, QSPI bit-order, eMMC 4-bit, RGMII (no swaps, delay self-consistent), ULPI (data order + CLK direction), BMI323 SPI, Zynq↔STM32 I2C, JTAG TAP, clocks/reset domains. This is the main result — the wiring of the chip-to-peripheral interfaces is sound.
> - ✅ **BOOT_MODE[2]/[0] no fixed POR strap → HIGH, CONFIRMED & VALID.** `R1`/`R6` are 10k *series* to STM32 PA7/PB2 with no rail pull; `PS_POR_B` is pulled to +3V3 by `R100`, releasing independent of the STM32 → cold-boot the BootROM can sample floating MIO4/MIO5. Fix: add ~20k strap (MIO4↓, MIO5↑) keeping R1/R6 series for STM32 override. **This supersedes Pass-3's INFO rating.**
> - ⚠️ **DONE no pull-up → real, MEDIUM (corrects Pass-1).** `ZYNQ_PL_DONE` has no pull-up (only Q3 gate/TP3/U2.T12); UG585 Table 6-21 requires an external pull-up to VCCO_0. The Q3 DONE-indicator can't pull high without it. Pass-1's "internal pull-up makes it fine" was optimistic. Fix: add pull-up to +3V3.
> - ❌ **PS_SRST_B 3.3V→1.8V "overdrive" (claimed HIGH) — DISMISSED.** The schematic carries an explicit **DESIGN NOTE: "configure …ZYNQ_PS_SRST… as open drain"** — so 3.3V open-drain + R94 1.8V pull-up is correct by design. Firmware-conformance only (matches Pass-2's ruling). Not a hardware defect.
> - ❌ **eMMC DAT4-7 floating (claimed MEDIUM) — reconciled DOWN.** 4-bit is the correct max for Zynq PS SDIO; DAT4-7 NC is right (Pass-2 already settled this). At most LOW.
>
> Net new actionable from this pass: **1 HIGH (boot-strap determinism)** + **1 MEDIUM (DONE pull-up)**. Everything else either confirms a bus is clean or was already covered. Full agent report below.

# SOM Interface & Wiring Audit

## Executive summary

Interface-level verification (every chip↔peripheral pin/bit/direction/protocol-level traced end-to-end against UG585 v1.7, the device datasheets, and the emitted netlist `/tmp/som_netlist.net`) **did find new wiring defects beyond the two known board-dead DDR CRITICALs**, but all of them are in the **boot/config/reset/strap supervision domain**, not in the high-speed data paths. The bulk-data interfaces are clean.

Counts by severity (NEW, beyond the prior-audit knowns):

| Severity | Count | Items |
|---|---|---|
| CRITICAL | 0 | — |
| HIGH | 3 | PS_SRST_B 3.3V-into-1.8V overdrive; PL DONE has no pull-up; BOOT_MODE[2]/[0] have no fixed POR strap (boot-device undefined at cold POR) |
| MEDIUM | 2 | (same boot-strap root cause, restated from the boot-determinism angle); eMMC DAT4–7 + DS left floating |
| LOW | 2 | BMI323 SPI lines no external idle pull; STM32 config supervisor open-loop (DONE/INIT_B not fed back) |
| INFO | 3 | U11 value W25Q128JVS vs WSON LCSC; eMMC RST MCU-owned; MIO6 PLL strap set indirectly via QSPI_CLK pull |

**Single most important NEW finding:** the boot-device select straps **BOOT_MODE[2] (MIO4) and BOOT_MODE[0] (MIO5) have no fixed pull resistor to any rail** — they are biased only through 10k *series* resistors out to STM32 GPIOs (PA7/PB2), while `PS_POR_B` is held high by R100→+3V3 and therefore releases on power-good **independent of STM32 state**. At a cold power-up where the STM32 has not yet driven the straps, the BootROM samples two floating boot-select bits and the boot source is undefined. This is the closest thing to a board-bring-up blocker in this pass.

**Clean interfaces — stated explicitly:** DDR addr/cmd/ctrl/clock (address A0–A14, BA0–2, RAS/CAS/WE/CS/CKE/ODT, CK_P/CK_N polarity, ZQ=240R, VREF=VDDQ/2) is **CLEAN**; QSPI bus bit-order is **CLEAN** (only the strap *bias mechanism* is suspect); eMMC 4-bit data path (D0–D3/CMD/CLK) is **CLEAN**; RGMII (all 12 data/ctrl + MDC/MDIO, delay strategy self-consistent) is **CLEAN**; ULPI/USB (8-bit data, DIR/STP/NXT/CLK direction, REFCLK level, RBIAS, DP/DM polarity) is **CLEAN**; BMI323 SPI4W (SDI/SDO/SCK/CS not swapped) is **CLEAN**; Zynq↔STM32 I2C0 is **CLEAN**; JTAG TAP (no TDI/TDO swap) is **CLEAN**; clocks/reset domains all match their banks.

---

## NEW confirmed wiring defects

### HIGH-1 — PS_SRST_B (1.8V VCCO_MIO1 input) driven directly by a 3.3V STM32 GPIO — input overdrive
- **What/where:** `NET ZYNQ_PS_SRST` = {R94.2 (10k), TP5.1, **U2.C9 [PS_SRST_B_501]**, **U9.26 [PB13]**}. R94.1 sits in `NET +1V8`. No series resistor, no level shifter between PB13 and PS_SRST_B. By contrast the sibling `NET ZYNQ_PS_POR` = {R100→+3V3, U2.B5, U9.PB12} — correctly matched to 3.3V.
- **Why:** UG585 Table 2-2 (verified, line ~2318): **PS_SRST_B `Voltage Node = VCCO_MIO1`**; on this SOM VCCO_MIO1 = +1V8 (R94 pulls to +1V8, consistent). The same table's CAUTION (line ~2304): "the allowable Vin High level voltage depends on the settings of … [IO_Type]/[DisableRcvr] … Damage to the input buffer can occur when the limits are exceeded." The STM32 runs on +3V3_SC and a push-pull GPIO swings to 3.3V — well above a 1.8V-banked input's recommended VIH (the absolute limit is set by the Zynq-7000 DC datasheet).
- **Impact:** If STM32 firmware configures PB13 as push-pull and drives it high, ~3.3V is forced into the 1.8V-domain PS_SRST_B input → long-term input-buffer damage / leakage / out-of-spec operation. Correctness then silently depends on firmware always using open-drain.
- **Fix:** Drive PB13 as **open-drain** (low / Hi-Z only) and let R94's 1.8V pull-up form the high level — mirroring the PS_POR_B 3.3V-domain approach; enforce in firmware. Or add an open-drain buffer / level shifter. A hard 3.3V push-pull drive is incompatible with the 1.8V bank.
- **Panel vote:** 3/3.

### HIGH-2 — PL DONE has no pull-up to VCCO_0; config-done can never read High
- **What/where:** `NET ZYNQ_PL_DONE` = {Q3.2 [G] (NMOS gate, high-Z), TP3.1, **U2.T12 [DONE_0]**}. There is **no pull-up resistor anywhere on the net** (verified — only 3 nodes).
- **Why:** UG585 Table 6-21 (verified verbatim, line 11409–11412): "DONE — Active-High open-drain output … The PL drives the DONE signal Low until the PL is successfully configured. **Board Connection: External 330 kΩ pull-up resistor to VCCO_0.**" VCCO_0 on this board = +3V3. DONE releases (tri-states) after config and *requires* an external pull-up to be read High.
- **Impact:** After successful PL configuration the DONE net floats instead of going High → the done-indicator LED (via Q3) never lights, and any supervisor/FSBL/JTAG-programmer/carrier logic polling DONE mis-reads "not done." Configuration itself still completes (the Low→release is internal); only done-status sensing is broken.
- **Fix:** Add a pull-up from `ZYNQ_PL_DONE` to +3V3 (VCCO_0) — 330k per UG585 (a stronger 4.7k–10k is commonly used and also fine).
- **Panel vote:** 3/3.

### HIGH-3 — BOOT_MODE[2] (MIO4) and BOOT_MODE[0] (MIO5) have NO fixed POR strap; boot device is undefined at cold POR
- **What/where:** `NET QSPI_D2{slash}BM2` = {R1.2 (10k), U11.3 [IO2], **U2.E4 [PS_MIO4]**}; `NET QSPI_D3{slash}BM0` = {R6.2 (10k), U11.7 [IO3], **U2.A3 [PS_MIO5]**}. R1.1/R6.1 do **not** go to a rail — they go to `NET ZYNQ_BMODE_2` (={R1.1, TP9, **U9.15 PA7**}) and `NET ZYNQ_BMODE_0` (={R6.1, TP10, **U9.19 PB2**}). So R1/R6 are 10k **series** isolators to STM32 GPIOs; neither MIO4 nor MIO5 has any pull to +3V3/GND. By contrast MIO2 (R76→GND), MIO3 (R77→GND), MIO6 (via QSPI_CLK→R13→GND) *are* statically strapped. `NET ZYNQ_PS_POR` is held high by R100→+3V3, so POR deasserts on power-good regardless of STM32 readiness.
- **Why:** UG585 §6.2.5 / Chapter 2 (verified, line ~2660): "The strapping pins are sampled a few PS_CLK clock cycles after the PS_POR_B reset signal de-asserts. **The board design ties these signals to VCC or ground using 20 KΩ pull-up and pull-down resistors.**" Per Table 6-4, Quad-SPI boot needs {MIO5,MIO4,MIO3} = {BOOT_MODE[0],[2],[1]} = {1,0,0} — i.e. **MIO5 must be pulled UP** and MIO4 pulled down. The Zynq provides no internal default on strap pins; ST confirms STM32 GPIOs are Hi-Z floating inputs out of the MCU's own reset.
- **Impact:** At a cold power cycle, if U9 firmware has not driven PA7=0 / PB2=1 before PS_POR_B releases, MIO4/MIO5 float and the BootROM samples indeterminate BOOT_MODE[2]/[0] → boot device undefined (may resolve to JTAG/NAND/SD/QSPI by noise/leakage). The board can fail to boot or boot from the wrong source on a fraction of power-ups. It is a race between U9 readiness and Zynq POR with no hardware QSPI fallback.
- **Fix (preferred = boots with no MCU):** Strap directly on the MIO pin and keep the STM32 series-isolated: add a ~20k pull-**down** on MIO4 (=0) and a ~20k pull-**up** on MIO5 (=1) to the bank rail, keeping R1/R6 as the dominant series so PA7/PB2 can still override. Alternative: change R100 to a pull-**down** so PS_POR_B defaults asserted (Zynq held in reset) until firmware sets the straps and releases PB12 — and verify the ordering. Also confirm U9 tri-states PA7/PB2 after POR sampling so they do not inject through 10k into flash IO2/IO3 during quad reads.
- **Panel vote:** 3/3. (The two MEDIUM entries "QSPI boot-mode straps…no passive pull" and "Boot-device straps MIO4/MIO5…no fail-safe default" are the same root cause restated from the boot-*determinism* angle; treat them as the MEDIUM-severity framing of HIGH-3, not independent defects.)

### MEDIUM — eMMC U7 DAT4–DAT7 and DS left floating (no pull/termination) on an 8-bit-capable part
- **What/where:** U7 = IS21ES08G (8-bit-capable eMMC). Verified single-node floating nets: `unconnected-(U7C-DAT4-PadB3)`, `…DAT5-PadB4`, `…DAT6-PadB5`, `…DAT7-PadB6`, `…DS-PadH5`. The 4-bit lower byte is correct: D0–D3/CMD each carry a 10k pull-up to +1V8 (R39–R43), CLK correctly un-pulled.
- **Why:** Per JEDEC eMMC, DAT lines are high-Z after reset; any DAT line not driven by the host must be biased to a defined level (pull-up to VCCQ conventional). DAT4–7/DS are real device I/O on this part, not true NC pins. The host can only run 4-bit anyway: the Zynq PS SDIO1 MIO mux exposes only DATA[0:3] (UG585 SDIO1 options DATA0={10,22,34,46}…DATA3={15,27,39,51}); there is no MIO path for DATA[4:7].
- **Impact:** Floating CMOS inputs on the eMMC die → idle leakage / possible indeterminate internal state / reduced EMC-SI margin (not boot-fatal). Also permanently caps throughput at 4-bit.
- **Fix:** Add 10k pull-ups to VCCQ(+1V8) on DAT4(B3)/DAT5(B4)/DAT6(B5)/DAT7(B6) and on DS(H5); pin the FSBL/u-boot eMMC bus width to 4-bit (no `MMC_CAP_8_BIT_DATA`). 8-bit on XC7Z020 would require routing CLK/CMD/DAT[7:0] via EMIO to PL pins — a respin, not a stuff option.
- **Panel vote:** 2/3.

### LOW — BMI323 SPI CSB (and SDX/SCX/SDO) have no external idle pull during the PL-unconfigured window
- **What/where:** `NET IO_L9_DQS_N_33` = {U14.12 [CSB], U2.Y21} — a pure 2-pin net, no resistor. SDX/SCX/SDO likewise pure point-to-point. PL SelectIO is tri-stated from power-up until the bitstream loads (can be 100s of ms–seconds).
- **Why:** Bosch BMI323 DS §7.2.1: powers up in I2C; "a rising edge on CSB is needed before starting SPI." During the float window CSB is held only by the internal 75/100/140k pull-up to VDDIO (keeps the safe I2C-default), and the first firmware CSB low→high supplies the SPI-arming edge — so the part won't latch the wrong protocol. Best practice is still an explicit external pull-up on CSB against pre-config noise.
- **Impact:** Not board-dead; functions once the PL drives the bus. Residual robustness risk only.
- **Fix:** Add ~10k pull-up on CSB to +VCCO_33 (=VDDIO), or constrain the PL IO with PULLUP + defined initial drive (no-cost FPGA-config alternative). No change to SDX/SCX/SDO required.
- **Panel vote:** 3/3.

### LOW — STM32 config supervisor is open-loop (DONE and INIT_B not routed back)
- **What/where:** STM32 drives PROGRAM_B (PA6→`ZYNQ_PL_PROGB`), PS_POR_B, PS_SRST_B, and the straps, but `ZYNQ_PL_DONE` (only Q3 gate + TP3) and `ZYNQ_PL_INITB` (only R99 4k7→+3V3 + TP2) reach **no** STM32 GPIO.
- **Why:** A controller that pulses PROGRAM_B normally monitors INIT_B (config-cleared/error) and DONE (complete) to sequence/detect failures — recommended supervisory practice (not strictly required by UG585 for boot to function).
- **Impact:** STM32 cannot detect a failed/aborted PL config or know when config finished → no recovery/retry/fault reporting from the system controller. Functional gap, not a boot-blocker.
- **Fix:** If respun, route DONE and INIT_B to spare STM32 GPIOs (both are 3.3V bank-0 config pins, compatible). Otherwise document that config supervision is open-loop.
- **Panel vote:** 3/3.

### INFO items
- **U11 value W25Q128JVS (SOIC) vs footprint+LCSC WSON (W25Q128JVEIQ, C401662):** label-only; same die/pinout/2.7–3.6V, footprint correctly WSON-8. Update the value string. (3/3)
- **eMMC RST_n owned by STM32 PC4** (`eMMC_~{RST}` = {R97→+1V8, U7.K5, U9.16/PC4}): single driver, pull-up holds it deasserted (JEDEC-safe), Zynq PS-SDIO has no RST MIO. Correct-but-unusual: Zynq cannot independently hardware-reset the eMMC. Document as MCU-owned. (2/3)
- **MIO6 PLL strap set indirectly via QSPI_CLK:** `NET QSPI_CLK_T/BM4` = {R95.2 (22R), U2.A4}; R95.1 joins `QSPI_CLK` which has R13(10k)→GND. Net MIO6 = 0 = PLL enabled (correct), but strapped through the shared clock node rather than a dedicated 20k. Reliable because the flash CLK is idle at strap sampling. Accept or add a dedicated 20k for clarity. (2/3)

---

## Per-interface verdict table

| Interface | Verdict | Key evidence |
|---|---|---|
| **DDR addr/cmd/ctrl/clk** | **CLEAN** | A0–A14 via 22R series R53–R67 (1:1 names), BA0–2 via R68/69/70, RAS/CAS/WE/CS/CKE/ODT each via series R to correct U1 pin; CK_P=U2.N4→U1.J7(CK), CK_N=U2.N5→U1.K7(CK#) correct polarity, R50=100R diff term; ZQ=U1.L8→R45 240R→GND; VREF=+0V675=VDDQ/2 to all four VREF pins. No swap/inversion/missing. (DDR x16-byte-lane + VRP/VRN R46/R47 swap are the *prior-audit* CRITICALs, excluded here.) |
| **QSPI (U11 W25Q128)** | **CLEAN bus / strap mechanism SUSPECT** | CS=MIO1, IO0=MIO2, IO1=MIO3, IO2=MIO4, IO3=MIO5, CLK=MIO6 — exact ascending bit-order, canonical QSPL0 single-device boot group (UG585 ~9968-9970), CS pull-up R44→+3V3, CLK 22R(R95)+10k(R13)→GND. Only defect = MIO4/MIO5 strap bias (HIGH-3). |
| **eMMC (U7 SDIO1)** | **DEFECT (MEDIUM)** | D0→MIO46, D1→MIO49, D2→MIO50, D3→MIO51, CMD→MIO47, CLK→MIO48 — each in its own UG585 SDIO1 index-locked set, pull-ups R39–R43→+1V8 (=VCCQ, bank 501), CLK un-pulled. DAT4–7+DS floating (MEDIUM). RST MCU-owned (INFO). |
| **RGMII (U3 RTL8211F)** | **CLEAN** | TXC=MIO16, TXD0–3=MIO17–20, TXCTL=MIO21, RXC=MIO22, RXD0–3=MIO23–26, RXCTL=MIO27, MDC=MIO52, MDIO=MIO53 (R14 1.5k→+1V8). No Tx/Rx group swap, no nibble swap; PHYAD=001; both 2ns delays sourced by PHY (rxdly/txdly straps up) → GEM must be plain `rgmii`. X2 25MHz 1.8Vpp amplitude is the *prior-audit* HIGH, excluded. |
| **ULPI (U5 USB3318)** | **CLEAN** | DATA0–7 → MIO32/33/34/35/28/37/38/39 (UG585 Table 15-50 1:1, no transposition); DIR=MIO29(in), NXT=MIO31(in), STP=MIO30(out); CLK = PHY CLKOUT→R22→MIO36(in) (output-clock mode correct); REFCLK 13MHz X1→R21, threshold scales with 1.8V VDD18 so 1.8Vpp compliant; RBIAS R24=8.06k; RESETB R5→+1V8; DP/DM polarity preserved to J1, not crossed with STM32 USB. |
| **BMI323 SPI (PL bank33)** | **CLEAN (LOW idle-pull note)** | SDI=pin14→Y21, SCK=pin13→Y22-area(AA22), SDO=pin1→AA21, CSB=pin12→Y21; MOSI/MISO and SCK/CS not swapped; INT1/INT2 on real PL IO; VDDIO=+VCCO_33 matches the PL bank rail. Only LOW = no external idle pull. |
| **Zynq↔STM32** | **CLEAN (I2C) / reset has HIGH-1** | I2C0 SCL=MIO14(via R96 22R)+R86 10k→+3V3, SDA=MIO15+R87 10k→+3V3; dedicated 2-node bus, no address collision, all 3.3V. PS_POR_B 3.3V-matched (correct); PS_SRST_B = HIGH-1 overdrive. |
| **Config/JTAG** | **DEFECT (DONE) / rest CLEAN** | TCK/TMS/TDI/TDO → bank-0 dedicated JTAG pins, TDO is output, no swap, route to J1. PROGRAM_B R98 4k7→+3V3 ✓, INIT_B R99 4k7→+3V3 ✓ (UG585 Table 6-21), CFGBVS=+3V3 ✓. **DONE = HIGH-2 (no 330k pull-up).** MIO4/5 straps = HIGH-3. VMODE: MIO7→R75→GND=LVCMOS33 (bank500=3V3 ✓), MIO8→R74→+3V3=LVCMOS18 (bank501=1V8 ✓) — consistent. |
| **Clocks/reset** | **CLEAN** | X1 13MHz(1V8)→USB REFCLK, X2 25MHz(1V8)→PHY EXT_CLK (XTAL_IN=GND, single-ended), X3 33MHz(3V3)→PS_CLK MIO bank500=3V3 (domain match), all 22R series, all EN tied to own Vdd (free-running). Resets: POR/SRST/PHY/USB/eMMC pulls all match their banks; DDR_RST R48 4k7→GND (asserted-safe); STM32_NRST RC. No clock on non-clock pin, no stuck reset, no domain mismatch (except SRST drive = HIGH-1). |
| **Pulls/term/power (cross)** | **CLEAN + reset domain HIGH-1** | Bank VCCO map: 500=+3V3, 501=+1V8, 502=+1V35; 13/33/34/35 carrier-supplied. All pull rails match their bank/peripheral I/O supply; decoupling present on every rail. RTL8211F INT/PMEB pulled to carrier +VCCO_35 = *prior-audit* LOW. |

---

## Rejected candidates (panel-killed)

1. **"MIO6 BOOT_MODE[4]/PLL strap floats at sampling" (HIGH, 0/3 — REFUTED).** `NET QSPI_CLK_T/BM4` = {R95.2 (22R series), U2.A4}; R95.1 joins `NET QSPI_CLK` = {R13.1 (10k), R95.1, TP11, U11.6 [CLK]}; R13.2 is in GND. So MIO6 *is* DC-held to 0 (PLL enabled) through the 22R+10k path; the flash CLK is idle at strap sampling. Not floating. (Captured as INFO instead.)
2. **"RTL8211F INT/PMEB pulled to carrier VCCO_35 → PHY overstress if 3.3V" (LOW, 0/3 — REFUTED).** Per the RTL8211F pin table, INT/PMEB is open-drain and tolerant; the receiver (Zynq bank-35 PL pin) shares the same +VCCO_35 pull rail, so it is domain-self-consistent. Already noted as a carrier-supplied documentation item in the prior audit.
3. **"eMMC on SDIO1 is non-bootable → eMMC boot fails silently" (INFO/MEDIUM, 1/3 — premises true, severity rejected).** Confirmed: eMMC is on SDIO1 (MIO46-51) which the BootROM cannot boot from (SD boot is hardcoded to SDIO0/MIO40-45 → carrier SD on J1). But primary boot is QSPI by design; FSBL mounts the eMMC afterward. Correct-but-noted topology, not a wiring defect → downgraded to a documentation INFO.
4. **"STM32 PA7/PB2 stay DC-coupled to flash IO2/IO3 through 10k" (LOW, 1/3).** Netlist reproduced exactly (R1/R6 are series), but the residual injection is folded into HIGH-3's fix note (tri-state PA7/PB2 after POR), so not raised as a standalone defect.

---

**Verification basis:** every NEW finding and every CLEAN verdict above was re-derived from `/tmp/som_netlist.net` / `/tmp/som_nets.txt` and cross-checked against `/tmp/ug585.txt` primary lines (Table 2-2 reset domains ~2300-2325; strap-20k/POR-sampling ~2658-2664; Table 6-21 DONE 330k @ 11409-11412) plus the device datasheets — no claim is taken on faith from the input JSON. Source files of record: `/Users/nicholasantoniades/Documents/GitHub/Zynq-SoM/som/Zynq_SoM.kicad_sch`, prior reports `/Users/nicholasantoniades/Documents/GitHub/Zynq-SoM/som/SOM_ELECTRICAL_AUDIT.md` and `/Users/nicholasantoniades/Documents/GitHub/Zynq-SoM/som/SOM_CARRIER_COORDINATION.md`.
