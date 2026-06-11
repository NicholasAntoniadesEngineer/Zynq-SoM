# Research dossier: camera_csi (stretch — research only, no netlist yet)

Date: 2026-06-11. Scope: Raspberry Pi 15-pin camera port (2-lane MIPI CSI-2)
on the carrier: FFC pinout, lane mapping onto SoM J3 bank-35 LVDS-capable
pairs, D-PHY-on-HR-bank reality check, gated 3V3 power, LCSC connector pick.
Connector stock/prices live-verified on the JLCPCB parts API 2026-06-11.
PLAN round-2 locked: "Camera: RPi 15-pin FFC, 2-lane MIPI CSI-2".

---

## 0. RPi 15-pin FFC pinout (public Raspberry Pi schematics) -> carrier nets

1.0 mm pitch, 15 pins, bottom-contact; cable contacts face the PCB.

| Pin | RPi name | Dir (cam) | Carrier net | Notes |
|-----|----------|-----------|-------------|-------|
| 1 | GND | — | GND | |
| 2 | CAM1_DN0 | out | CAM_D0_N | data lane 0 (note: N before P on the FFC) |
| 3 | CAM1_DP0 | out | CAM_D0_P | |
| 4 | GND | — | GND | |
| 5 | CAM1_DN1 | out | CAM_D1_N | data lane 1 |
| 6 | CAM1_DP1 | out | CAM_D1_P | |
| 7 | GND | — | GND | |
| 8 | CAM1_CN | out | CAM_CLK_N | clock lane |
| 9 | CAM1_CP | out | CAM_CLK_P | |
| 10 | GND | — | GND | |
| 11 | CAM_GPIO0 | in | CAM_EN | module power-enable/shutdown (v2 uses this) |
| 12 | CAM_GPIO1 | in | CAM_LED | LED indicator (v1 only; keep routed) |
| 13 | SCL0 | in | CAM_SCL | control I2C, 3.3 V |
| 14 | SDA0 | bidir | CAM_SDA | |
| 15 | 3V3 | in | +3V3_CAM | gated rail, ~250 mA (V2 module typ; budget 300 mA) |

D-PHY pairs are NOT polarity-swappable — P to P, N to N, no exceptions.

## 1. Lane mapping -> J3 bank 35 (from carrier/som_interface.json)

Bank 35 on J3 exposes 30 IOs incl. 4 clock-capable pairs (L11_SRCC,
L12_MRCC, L13_MRCC, L14_SRCC). No subsystem uses ANY bank-35 pin today
(grep carrier/subsystems/*.py: zero `_35` hits) — clean slate.

| Lane | Carrier nets | SoM nets (verbatim) | J3 pins | Why |
|------|--------------|---------------------|---------|-----|
| Clock | CAM_CLK_P/N | IO_L13_MRCC_P_35 / IO_L13_MRCC_N_35 | 9 / 11 | MRCC -> drives BUFR/PLL for the D-PHY RX clocking |
| Data 0 | CAM_D0_P/N | IO_L10_P_35 / IO_L10_N_35 | 5 / 7 | plain pair physically flanking the clock pins |
| Data 1 | CAM_D1_P/N | IO_L15_DQS_P_35 / IO_L15_DQS_N_35 | 17 / 15 | DQS pair (fine as data), other flank — compact J3.5-17 group for length matching |

Ledger after camera: bank 35 keeps 24 IOs incl. 3 clock pairs (L11_SRCC,
L12_MRCC, L14_SRCC) free.

### D-PHY on a 7-series HR bank — the honest part (XAPP894)
Zynq-7020 HR banks have no native MIPI D-PHY receiver. The standard solution
(Xilinx XAPP894 "D-PHY Solutions", used by the Xilinx MIPI CSI-2 RX
Subsystem in "7-series + external passives" mode, and by Digilent's Pcam
ports) is:

- **HS RX**: IOSTANDARD LVDS_25 on a bank with **VCCO_35 = 2.5 V**, external
  100R differential termination at the FPGA end of each pair. HR-bank D-PHY
  RX tops out around ~800 Mb/s/lane — 2 lanes cover IMX219 1080p30/8 MP
  stills profiles (the RPi V2 default modes).
- **LP RX** (needed for proper frame-start protocol): XAPP894's resistor
  divider taps each line into additional single-ended inputs. That costs up
  to 4 extra bank-35 pins (LP-CLK_N is optional). Candidate allocation if
  implemented: IO_L18_P/N_35 (J3.27/25) + IO_L16_P/N_35 (J3.31/29).
  Minimal-viable alternative: video-only capture with fixed timing and LP
  events inferred — works for continuous streaming, fragile across sensor
  resets; rev A should place the XAPP894 dividers (passives are cheap, DNP
  optional).
- **CONSEQUENCE — rail map entry**: +VCCO_35 = **2.5 V from a local LDO**
  (same pattern as the FMC VADJ decision in PLAN round 2; AP2112K-2.5 class,
  e.g. AP2112K-2.5TRG1 — same family already in parts/ as the 1V8). Bank 35
  is then 2.5 V-only: nothing 3.3 V may ever be allocated there. CAM_SCL/
  SDA/EN/LED therefore must NOT land on bank 35.

### Control signals -> J3 bank 33 (3.3 V)
CAM_SCL, CAM_SDA, CAM_EN, CAM_LED are 3.3 V logic -> route to 4 of the 10
J3 bank-33 IOs (+VCCO_33 = +3V3 rail-map entry, shared with J2's bank-33
half). I2C pull-ups 4k7 (C23162 Basic) to **+3V3_CAM, the GATED rail** — a
powered-down camera must not be back-fed through its bus pull-ups. The
camera I2C is a dedicated Zynq-fabric bus (AXI IIC / PS I2C via EMIO), NOT
the STM32_I2C2 bus (different controller domain; the 0x20/0x22/0x40/0x41
map in power_mon.md is unaffected; camera sensor 0x10 lives on its own bus).

## 2. Power: +3V3_CAM (bring-up-gated)
SY6280-class load-switch cell on the bringup sheet (same contract as
+3V3_PMOD / +3V3_SD / +3V3_USER_LED), budget 300 mA. At the connector:
100n + 10u (C1591 + C15850, the wave-1 pair). CAM_EN additionally gives a
logic-level shutdown independent of the rail gate.

## 3. Connector (live-verified 2026-06-11)

| Item | MPN | LCSC | Stock seen | Lib | Unit @1 |
|------|-----|------|-----------:|-----|---------|
| RPi-reference part (RPi forums-confirmed): 1.0 mm 15P FFC, slide lock | Amphenol ICC SFW15R-2STE1LF | C3167933 | **111** | Extended | $0.80 |
| Committed pick: same SFW15R family, bottom contact, healthy stock | Amphenol ICC SFW15R-1STE1LF | C3168538 | 4,000 | Extended | $0.58 |

No 1.0 mm 15P bottom-contact clone with real stock surfaced on the JLC API
(the AFC01 family the LCD uses is 0.5 mm pitch — NOT cable-compatible).
VERIFY before netlist authoring: the -1STE1LF vs -2STE1LF actuator/contact
difference against the Amphenol SFW drawing AND the RPi cable orientation
(contacts toward PCB); if -1STE1LF's contact side mismatches, order
C3167933 early (111 units is ghost-risk territory — preflight re-check).

## 4. Future netlist sketch (for the authoring pass — NOT built yet)
J1(SFW15R) pins 2/3/5/6/8/9 -> 100R diff terms live FPGA-side per XAPP894
(layout note: terminations at the SoM connector end of the traces, not at
the FFC) -> ports CAM_* with `port_type(kind="diff_pair", impedance=100)`;
pins 13/14 + pull-ups to +3V3_CAM; 11/12 plain ports; 15 -> +3V3_CAM port
(expect bringup); 1/4/7/10 -> GND. ESD: optional TPD4E05U06 across the
FFC-facing lines (stuffing option, rev A may omit — short internal cable).

## Risks / open items
1. **+VCCO_35 = 2.5 V** is a NEW rail (local LDO) — must be locked in the
   rail map before any other subsystem claims bank 35, and before wave-3 J3
   sheet generation.
2. **HR-bank D-PHY is a hack** (XAPP894 passives, ~800 Mb/s/lane): fine for
   the V2 (IMX219) defaults; full 4-lane/high-rate cameras (HQ IMX477 max
   modes) are out of scope for this port.
3. **Connector contact orientation** (section 3) — verify before authoring;
   exact-part stock is thin.
4. **LP-RX pin spend** (4 more bank-35 pins) — decide DNP-vs-stuffed at
   authoring; dossier reserves L18 + L16 pairs.
5. 22-pin (Pi Zero/5-style) cameras need a 22->15 adapter cable — by
   design, not a carrier change.

Sources: Raspberry Pi published schematics + camera mechanical/pinout docs
(datasheets.raspberrypi.com, public); RPi forums CSI/DSI connector thread
(SFW15R-2STE1LF); Xilinx XAPP894 "D-PHY Solutions" + MIPI CSI-2 RX
Subsystem PG232 (7-series external-passives mode); Digilent Pcam 5C / Zybo
Z7 reference design (HR-bank CSI precedent); JLCPCB selectSmtComponentList
API (live stock, 2026-06-11); carrier/som_interface.json (J3 bank-35/33
inventory); carrier/PLAN.md (camera + VADJ-pattern decisions).
