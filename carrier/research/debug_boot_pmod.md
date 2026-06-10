# Research dossier: debug_boot_pmod (wave 2)

Date: 2026-06-10. Scope: (a) Zynq JTAG header, (b) STM32 SWD header, (c) boot-mode
switches, (d) 2x PMOD ports. All facts below verified against `som/Zynq_SoM.kicad_pcb`
(pad->net extraction), `carrier/som_interface.json`, and live LCSC/JLCPCB stock APIs
on 2026-06-10. Locked context from `carrier/PLAN.md`: rails +5V/+3V3/+1V8, DIP+STM32
bring-up, JLC Basic preferred, 4-layer JLC7628.

---

## 0. SoM-side ground truth (verified from the SoM netlist, not assumed)

| Net (J1 name, exact)  | J1 pin | SoM-side connection (verified)                          |
|-----------------------|--------|---------------------------------------------------------|
| `ZYNQ_TCK`            | 64     | Zynq U2 ball G11 (bank-0 dedicated JTAG), no SoM pulls   |
| `ZYNQ_TMS`            | 66     | Zynq U2 ball G12, no SoM pulls                           |
| `ZYNQ_TDO`            | 68     | Zynq U2 ball G14, no SoM pulls                           |
| `ZYNQ_TDI`            | 70     | Zynq U2 ball H13, no SoM pulls                           |
| `STM32_GPIO6`         | 45     | STM32G431CBU (U9) pin 36 = **PA13 = SWDIO**              |
| `STM32_GPIO5`         | 53     | STM32G431CBU (U9) pin 37 = **PA14 = SWCLK**              |
| `STM32_NRST`          | 47     | U9 NRST (pin 7); SoM has R3 1k5 pull-up to +3V3_SC + C13 470n to GND |
| `STM32_BOOT0`         | 57     | U9 PB8/BOOT0 (pin 46); SoM has R4 1k5 pull-DOWN to GND   |
| `+3V3_SC`             | 37     | STM32 system-controller rail (always-on, separate from main +3V3) |
| `ZYNQ_PS_MIO7/VM0`    | 40     | Zynq D5; SoM strap R75 10k to **GND** -> MIO bank 500 = 3.3V mode |
| `ZYNQ_PS_MIO8\VM1`    | 36     | Zynq E5; SoM strap R74 10k to **+3V3** -> MIO bank 501 = 1.8V mode |

Boot-device mode: **NOT exposed on J1.** The Zynq mode straps live on the SoM QSPI nets
(`QSPI_D3/BM0`, `QSPI_D1/BM1`, `QSPI_D2/BM2`, `QSPI_D0/BM3`, `QSPI_CLK_T/BM4`).
`ZYNQ_BMODE_0` and `ZYNQ_BMODE_2` are driven by the SoM STM32 (U9 pins 19/15) through
10k resistors (R6/R1); SoM design note: *"STM32 controls BOOT_MODE[0,2] to enable JTAG,
SD or QSPI boot modes"*. `ZYNQ_PS_POR`/`ZYNQ_PS_SRST` are also STM32-driven and not on J1.
Zynq JTAG bank: VCCO_0 (U2 ball T10) = **+3V3** on the SoM -> JTAG logic level is 3.3V.

Consequences for the carrier:
1. The carrier **cannot strap Zynq boot mode directly**; it requests boot mode from the
   SoM STM32 (via GPIO straps the SC firmware reads) — see section (c).
2. VM0/VM1 are already strapped on-SoM (10k). Carrier: **no-connect** (optionally test
   points). Do NOT re-strap; a carrier 1k strap would override 10k if ever needed (rework).
3. The SoM STM32's SWD lives on J1 under the names `STM32_GPIO6` (SWDIO) and
   `STM32_GPIO5` (SWCLK) — these two J1 nets are RESERVED for debug; the bring-up
   subsystem must not claim them as override GPIOs, and SC firmware must never
   reconfigure PA13/PA14.
4. The old `boards/carrier` sheets used stale names (`ZYNQ_PS_JTAG_TCK`,
   `ZYNQ_BOOT_MODE_0..3`, FX10A pinout) — all superseded by the names above.

---

## (a) Zynq JTAG — Xilinx 2x7 2.00 mm header

### Pinout (verified: AMD UG1514 "JTAG Target Interface" + Digilent JTAG-HS3 docs)
Keyed shrouded 2x7, 2.00 mm pitch. Odd pins on one row, even on the other.

| Pin | Signal | Carrier net            | Pin | Signal | Carrier net |
|-----|--------|------------------------|-----|--------|-------------|
| 1   | GND    | GND                    | 2   | VREF   | +3V3 (powers probe buffers; must equal VCCO_0 = 3.3V) |
| 3   | GND    | GND                    | 4   | TMS    | ZYNQ_TMS (J1.66) |
| 5   | GND    | GND                    | 6   | TCK    | ZYNQ_TCK (J1.64) |
| 7   | GND    | GND                    | 8   | TDO    | ZYNQ_TDO (J1.68) |
| 9   | GND    | GND                    | 10  | TDI    | ZYNQ_TDI (J1.70) |
| 11  | GND    | GND                    | 12  | NC     | author no-connect |
| 13  | GND (PGND) | GND                | 14  | SRST   | **NC** (see note) |

Pin 14 note: on Zynq targets UG1514 wires pin 14 to PS_SRST_B. This SoM does **not**
export PS_SRST_B on J1 (it is owned by the SoM STM32, TP5 on-module), so pin 14 is an
explicit no-connect on the carrier. Debugger-initiated PS reset happens via the SC
(XSDB/JTAG can still issue internal resets; this is the standard SoM trade-off).

Reference circuit (datasheet-style, complete):
- J: 2x7 2.00 mm shrouded box header, wired per table above.
- R 4k7 pull-up TMS -> +3V3 and R 4k7 pull-up TDI -> +3V3 (Zynq dedicated JTAG pins
  have weak internal pull-ups; these externals are cheap insurance against a floating
  bus when no probe is attached — keep them, they are 2x C23162 Basic).
- No series resistors required at 2 mm header lengths; probe drives 1.8–5 V, 30 Mbit/s.
- 100n decoupling not required (no active parts).

### Parts (live-verified 2026-06-10)
| Item | MPN | LCSC | Stock seen | Lib | Unit @1 |
|------|-----|------|-----------:|-----|---------|
| 2x7 2.00 mm shrouded header, THT vertical (Xilinx-reference part, named in UG1514) | Molex 87831-1420 (`878311420`) | C240854 | 5,997 | Extended | $1.43 |
| Budget alternate, same 2x7 2 mm IDC-box format | MINTRON MTB11-14S | C376113 | 3,591 | Extended | $0.20 |
| TMS/TDI pull-ups 4.7k 0603 | UNI-ROYAL 0603WAF4701T5E | C23162 | 10,324,142 | **Basic** | $0.0014 |

Recommendation: Molex C240854 (it is the exact connector AMD lists for SmartLynq/
Platform Cable/JTAG-HS3 compatibility; stock healthy). MTB11-14S as BOM-cost fallback.

---

## (b) STM32 SWD — ARM Cortex Debug 10-pin, 1.27 mm

### Pinout (verified: ARM "Cortex-M Debug Connectors" doc, pinout read from the PDF)
2x5, 1.27 mm (0.05"), keyed shroud, pin 7 removed as KEY.

| Pin | Signal     | Carrier net                                  |
|-----|------------|----------------------------------------------|
| 1   | VTref      | **+3V3_SC** (J1.37 — the SC's always-on rail, so SWD works with main rails down: exactly what bring-up needs) |
| 2   | SWDIO/TMS  | STM32_GPIO6 (J1.45, = PA13)                   |
| 3   | GND        | GND                                           |
| 4   | SWCLK/TCK  | STM32_GPIO5 (J1.53, = PA14)                   |
| 5   | GND        | GND                                           |
| 6   | SWO/TDO    | NC (G431 SWO = PB3 is unconnected on the SoM — pad 41 `unconnected-(U9-PB3)`) |
| 7   | KEY        | no pin                                        |
| 8   | NC/TDI     | NC                                            |
| 9   | GNDDetect  | GND                                           |
| 10  | nRESET     | STM32_NRST (J1.47; SoM already has 1k5 PU + 470n) |

Reference circuit: header only, wired as above; no pulls needed on SWDIO/SWCLK
(PA13/PA14 reset state is SWD with internal pulls per STM32G4 datasheet; SoM provides
the NRST RC). JTAG to the G431 is not possible over this header (SWD-only) — fine,
all probes (ST-LINK, J-Link, CMSIS-DAP) speak SWD on this connector.

### Parts (live-verified 2026-06-10)
| Item | MPN | LCSC | Stock seen | Lib | Unit @1 |
|------|-----|------|-----------:|-----|---------|
| 1.27 mm 2x5 keyed box header, SMD vertical | hanxia HX JN1.27-2x5 TP H4.9 | C42372555 | 11,124 | Extended | $0.22 |
| Same, THT vertical (alternate) | hanxia HX JN1.27-2x5P ZZ H4.9 | C42372547 | 13,128 | Extended | $0.17 |
| Name-brand alternate (ARM-doc reference part) | Samtec FTSH-105-01-L-DV | C5199898 | 42 | Extended | $1.44 |

Recommendation: hanxia SMD (C42372555). Samtec stock (42) is too thin to baseline.
Note for footprint: verify the clone's shroud key matches the ARM 10-pin ribbon
(hanxia JN series is the standard keyed box; LCSC datasheet drawing confirms key slot).

---

## (c) Boot-mode switches

Because boot-device straps are on-SoM and STM32-driven (section 0), the carrier
"boot_switches" subsystem is **request straps + STM32 boot control**, not Zynq straps:

Reference circuit:
1. **SW DIP-4** (single 4-position DIP, SPST to GND unless noted):
   - Pos 1 — `STM32_BOOT0` (J1.57): switch to **+3V3_SC through 100R series**.
     SoM has 1k5 pull-down, so closed gives 3.3V x 1500/1600 = 3.1V at BOOT0 (VIH ok),
     open gives 0. Closed + reset = G431 system bootloader -> **USB DFU over the
     carrier's USB-C** (STM32_USB_D_P/N are already routed J1 -> Type-C).
   - Pos 2 — `ZYNQ_BOOTSEL0` request strap -> `STM32_GPIO7` (J1.59, U9 PB10).
   - Pos 3 — `ZYNQ_BOOTSEL1` request strap -> `STM32_GPIO8` (J1.54, U9 PB11).
     Pos 2/3 close to GND; add 10k pull-up to +3V3_SC on each (C25804 Basic) so the
     level is defined before SC firmware enables internal pulls. SC firmware decodes
     00/01/10/11 -> JTAG / QSPI / SD / (reserved) and drives ZYNQ_BMODE_0/2 on-module.
   - Pos 4 — spare, to GND with 10k pull-up to +3V3_SC, labeled net `BOOT_SPARE`
     (reserved; do not repurpose for bring-up rail ENs — those get their own DIPs).
2. **Reset button**: momentary tact switch `STM32_NRST` -> GND (debounce RC already
   on the SoM). Resetting the SC re-runs its power/boot sequencing = whole-system reset.
3. **VM0/VM1**: no parts. Optional two test points on `ZYNQ_PS_MIO7/VM0` /
   `ZYNQ_PS_MIO8\VM1` for bring-up probing only.

Firmware contract to record in the SC repo: GPIO7/8 sampled at SC boot as BOOTSEL[1:0];
PA13/PA14 stay SWD; BOOT0 owned by the DIP.

### Parts (live-verified 2026-06-10)
| Item | MPN | LCSC | Stock seen | Lib | Unit @1 |
|------|-----|------|-----------:|-----|---------|
| DIP-4 switch, SMD 1.27 mm gull-wing | XKB DSHP04TS-S | C319050 | 62,021 | Extended | $0.48 |
| Tact switch 5.1x5.1 SMD (reset) | XKB TS-1187A-B-A-B | C318884 | 1,830,400 | **Basic** | $0.020 |
| 10k 0603 pull-ups (x3) | UNI-ROYAL 0603WAF1002T5E | C25804 | 3,983,200 | **Basic** | $0.0011 |
| 100R 0603 BOOT0 series | UNI-ROYAL 0603WAF1000T5E | C22775 | 8,921,060 | **Basic** | $0.0019 |

---

## (d) PMOD — 2x standard 12-pin host ports

### Spec facts (verified: Digilent Pmod Interface Specification, rev 2020-10-28, read from PDF)
- Host port = **12-pin (2x6) right-angle FEMALE, 2.54 mm, at board edge**; straight
  female inboard is also allowed. Adjacent ports on 0.9" (22.86 mm) centers.
- Host pin numbering is Pmod-specific (NOT alternating odd/even): **top row 1-6,
  bottom row 7-12**; 1-4 = IO1-IO4, 5 = GND, 6 = VCC, 7-10 = IO5-IO8, 11 = GND,
  12 = VCC. The schgen symbol/footprint must use this numbering, not the generic
  KiCad 2x6 zigzag.
- Power: fixed 3.3V is an allowed subset (no 5V switching). Budget ~100 mA per module.
- Protection: standard Digilent host ports use **200R series resistors** on every IO
  (+ ESD diodes); logic is LVCMOS33/LVTTL.

### Carrier implementation
- Signals: 16 single-ended PL IOs from **J2 bank 13** as 8 full LVDS-capable pairs
  (keeps pairs intact, avoids MRCC/SRCC clock pins). REQUIRES the carrier rail
  decision **`+VCCO_13` = +3V3** (record in the rail map; conflicts with any plan to
  put bank 13 at another voltage).
- Per IO: 200R 0603 series (C8218 Basic) between the J2 net and the connector pin.
- VCC pins: feed from the bring-up-gated PMOD rail net `+3V3_PMOD` (load-switch
  subsystem owns the gate per PLAN; if PMOD is not given its own gate, alias to +3V3).
  100n + 10u decoupling at each port's VCC (same Basic 0603 parts wave-1 already uses).
- Optional ESD (stuffing option, matches "standard ports have ESD diodes"):
  1x SRV05-4 per port across IO1-4 or omit on rev A.

### Pin map (exact nets from `carrier/som_interface.json`)
PMOD0:
| Pmod pin | Signal | Net (SoM side) | J2 pin | | Pmod pin | Signal | Net (SoM side) | J2 pin |
|---|---|---|---|---|---|---|---|---|
| 1 | IO1 | IO_L2_P_13 | 20 | | 7  | IO5 | IO_L4_P_13 | 61 |
| 2 | IO2 | IO_L2_N_13 | 14 | | 8  | IO6 | IO_L4_N_13 | 63 |
| 3 | IO3 | IO_L3_P_13 | 18 | | 9  | IO7 | IO_L5P_13  | 38 |
| 4 | IO4 | IO_L3_N_13 | 43 | | 10 | IO8 | IO_L5_N_13 | 24 |
| 5 | GND | GND | — | | 11 | GND | GND | — |
| 6 | VCC | +3V3_PMOD | — | | 12 | VCC | +3V3_PMOD | — |

PMOD1:
| Pmod pin | Signal | Net (SoM side) | J2 pin | | Pmod pin | Signal | Net (SoM side) | J2 pin |
|---|---|---|---|---|---|---|---|---|
| 1 | IO1 | IO_L7_P_13 | 62 | | 7  | IO5 | IO_L9_DQS_P_13 | 50 |
| 2 | IO2 | IO_L7_N_13 | 64 | | 8  | IO6 | IO_L9_DQS_N_13 | 48 |
| 3 | IO3 | IO_L8_P_13 | 58 | | 9  | IO7 | IO_L10_P_13    | 53 |
| 4 | IO4 | IO_L8_N_13 | 60 | | 10 | IO8 | IO_L10_N_13    | 51 |
| 5 | GND | GND | — | | 11 | GND | GND | — |
| 6 | VCC | +3V3_PMOD | — | | 12 | VCC | +3V3_PMOD | — |

(Note the SoM symbol quirk: `IO_L5P_13` and `IO_L1P_13` have no underscore before P —
use the strings exactly as in som_interface.json.)

Connector-side internal nets: `PMOD0_IO1..IO8`, `PMOD1_IO1..IO8` (spec-aligned
1-based; the old boards/ sheets' zero-based `PMOD0_IO0..7` is legacy and dies with them).

### Parts (live-verified 2026-06-10)
| Item | MPN | LCSC | Stock seen | Lib | Unit @1 |
|------|-----|------|-----------:|-----|---------|
| 2x6 right-angle female 2.54 mm (spec-exact host socket) | CONNFLY DS1024-2x6R2 | C49284652 | **45** | Extended | $0.14 |
| Fallback: 2x6 straight female 2.54 mm (allowed by spec, healthy stock) | BOOMELE 2.54-2*6P | C36191 | 1,968 | Extended | $0.13 |
| 200R 0603 series (x16) | UNI-ROYAL 0603WAF2000T5E | C8218 | 4,135,653 | **Basic** | $0.0015 |
| Optional ESD array (x2) | SEMTECH SRV05-4.TCT | C13612 | 89,474 | Extended | $0.15 |

Stock risk: DS1024-2x6R2 at 45 units covers a proto run (2/board) but is a ghost-risk
part — preflight must re-check; the straight-female BOOMELE C36191 is the committed
fallback (spec-legal "straight female connector inboard from the board edge").

---

## PORT list (schgen subsystem ports — names = J1/J2 nets from som_interface.json)

`jtag_swd.py` (or split `zynq_jtag.py` + `stm32_swd.py`):
- ZYNQ_TCK, ZYNQ_TMS, ZYNQ_TDI, ZYNQ_TDO            (J1.64/66/70/68)
- STM32_GPIO6 (SWDIO), STM32_GPIO5 (SWCLK), STM32_NRST (J1.45/53/47)
- +3V3, +3V3_SC, GND

`boot_switches.py`:
- STM32_BOOT0, STM32_NRST, STM32_GPIO7, STM32_GPIO8  (J1.57/47/59/54)
- +3V3_SC, GND
- (test-point only, optional): ZYNQ_PS_MIO7/VM0, ZYNQ_PS_MIO8\VM1

`pmod.py`:
- IO_L2_P_13, IO_L2_N_13, IO_L3_P_13, IO_L3_N_13, IO_L4_P_13, IO_L4_N_13,
  IO_L5P_13, IO_L5_N_13 (PMOD0)
- IO_L7_P_13, IO_L7_N_13, IO_L8_P_13, IO_L8_N_13, IO_L9_DQS_P_13, IO_L9_DQS_N_13,
  IO_L10_P_13, IO_L10_N_13 (PMOD1)
- +3V3_PMOD (gated; alias +3V3 if no gate), GND

Shared-net notes: STM32_NRST appears in BOTH jtag_swd (header pin 10) and
boot_switches (reset button) — same net, the linker must merge, not error.
`ZYNQ_PS_MIO8\VM1` contains a backslash in the SoM source — escape carefully in
generated sheets.

## Risks / open items
1. **DS1024-2x6R2 stock (45)** — order immediately or fall back to straight female.
2. **Bank-13 rail**: +VCCO_13 = +3V3 must be locked in the rail map before wave-3 J2
   sheet generation; PMOD dies at any other voltage.
3. **GPIO budget**: this dossier consumes STM32_GPIO5/6 (SWD, reserved) and 7/8
   (BOOTSEL). Bring-up override subsystem is left STM32_GPIO1-4 + DAC1/2 — confirm
   sufficiency in the bringup dossier before freezing.
4. **SC firmware contract** (BOOTSEL decode, PA13/14 untouched) must be written down
   in the SoM repo; hardware here is useless without it.
5. All connectors are JLC Extended (normal — Basic library has almost no connectors);
   Extended-reel count for this group: 4 (JTAG hdr, SWD hdr, DIP-4, PMOD socket)
   + optional SRV05-4.
6. JTAG pin 14 = NC means no probe-driven PS_SRST; if hard-reset-from-probe is ever
   required, a future SoM rev must route PS_SRST_B to J1.

Sources: AMD UG1514 (JTAG Target Interface, docs.amd.com); ARM "Cortex-M Debug
Connectors" (documentation-service.arm.com 5fce6c49); Digilent Pmod Interface
Specification rev 2020-10-28 (digilent.com); Digilent JTAG-HS3 RM; LCSC
wmsc.lcsc.com product API + JLCPCB selectSmtComponentList API (stock/Basic-Extended,
queried 2026-06-10); som/Zynq_SoM.kicad_pcb + som/schematic/* (pad-net extraction).
