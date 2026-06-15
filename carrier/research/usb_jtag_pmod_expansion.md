# Research dossier: Stream-C debug bridge + Pmod expansion

Date: 2026-06-15. Scope: two new feature sheets —
  (C1) a cable-free USB-JTAG/UART debug bridge (self-powered + isolated), and
  (C2) a Digilent Pmod (2x6, 3.3 V) IO expansion port.
All part stock figures live-verified on the JLCPCB parts API on the date above;
all PL-pin allocations cross-checked pin-for-pin against `carrier/som_interface
.json` + `carrier/som_conn_gen.py` (FUNCTION_MAP / VCCO / PUDC) + every existing
subsystem's port set BEFORE claiming (the eight Pmod pairs + the UART pair read
"unclaimed (wave-3 function map)" in the prior XDC — consumed by NO other sheet).

Sheets: `carrier/subsystems/usb_jtag.py`, `carrier/subsystems/usb_jtag_connector
.py`, `carrier/subsystems/pmod_expansion.py`. Board: 30 -> 33 sheets (C1 is two
sheets per the carrier "connectors get their own sheet" idiom; see §4).

---

## C1 — USB-JTAG/UART debug bridge

### Part choice: CH347T, not FT2232H

The FT2232H is the canonical FTDI dual-channel JTAG+UART bridge and was the first
pick (FT2232HL C27882, 3,463 in stock; + a 93LC56B EEPROM C615922; + a 12 MHz
crystal C9002). It was REJECTED on a hard placer limit, not an electrical one:
the FT2232H is a **64-pin LQFP** — by far the largest IC on the carrier (next
biggest is 25 pins) — and the schgen auto-placer's escape-lane router cannot
route a 64-pin part. This was proven minimally: even a power-only FT2232H (just
VCCIO/VCORE/GND + a single decoupling cap, every signal pin NC) fails to route
(`+3V3 vs VCORE` rail-fan contention, VCORE spread across three LQFP edges). It
is a genuine engine gap, not a density the netlist can shed, so it could not be
authored around (and "redraw the part to fit the tool" is forbidden).

**CH347T (C5122332, TSSOP-20, 1,953 in stock)** is the direct, widely-used HS
USB->JTAG+UART alternative — the standard low-cost FPGA/CPU programmer chip (WCH).
Per its datasheet (v1A) **MODE 3** = "USB to high-speed single serial port + USB
to JTAG port" — exactly a JTAG programmer + a console UART in one part. It is
much smaller, needs far fewer support parts, and its TSSOP side-only pins place
cleanly. Decisive advantages vs the FT2232H beyond pin count:
  - **built-in config EEPROM** (no external 93C56 — DS §5.7),
  - **built-in USB-PHY + 1.5k pull-up + series matching** (UD+/UD- go DIRECT to
    the bus; the DS FORBIDS a series R on the data lines — DS p.3 note),
  - **built-in power-on reset** (RST# has an internal pull-up; no external RC).
External parts reduce to: an 8 MHz crystal + 22 pF caps (DS §5.1), a 3.3 V LDO,
and VCC decoupling. The FT2232HL/93LC56/12 MHz-crystal parts were removed.

### MODE 3 strap (JTAG + UART)

The CH347 latches its working mode at power-on from DTR1 (pin 10) and RTS1 (pin
13) — DS §5.2 table. MODE 3 = "DTR1 pulls down low, RTS1 pulls down low". Both
pins carry a 10k pulldown to GND on the bridge sheet; since both have ~40k
internal pull-ups, the 10k externals dominate at reset. So the bridge always
enumerates as one UART + one JTAG TAP.

### MODE-3 pin map (DS §4.6)
| Function | CH347 pin | Notes |
|----------|-----------|-------|
| TCK | 6 | JTAG clock out -> buffer -> ZYNQ_TCK |
| TMS | 5 | JTAG mode out  -> buffer -> ZYNQ_TMS |
| TDI | 7 | JTAG data out  -> buffer -> ZYNQ_TDI |
| TDO | 8 | JTAG data IN (internal pull-up) <- buffer <- ZYNQ_TDO |
| TRST| 9 | NC — the Zynq dedicated-JTAG bank has no TRST; OPTIONAL per DS §5.6 |
| TXD1| 3 | UART1 console TX -> DBG_UART_RXD (Zynq RXD) |
| RXD1| 4 | UART1 console RX <- DBG_UART_TXD (Zynq TXD) |
| VCC | 14| +3V3_DBG, 100n decap (single 3.3 V supply) |
| GND | 18| |
| UD+/UD- | 17/16 | direct to the protected bus pair |
| XI/XO | 19/20 | 8 MHz crystal + 22p |
| RST# | 1 | 10k pull-up; built-in POR (waive_reset, no RC) |

### Power: SELF-POWERED ISLAND (constraint C1)

The bridge runs entirely off `+5V_DBG` — the debug cable's own USB VBUS, brought
in by the USB-C receptacle — regulated to `+3V3_DBG` by U4 (AP2112K-3.3, C51118,
the carrier's standard LDO family; power.py uses the 1.8 V sibling). NOTHING on
this bridge touches a carrier rail. Consequences, both required by C1:
  - the bridge is ALIVE only while the debug cable is plugged (it is +5V_DBG-
    powered — no cable, no power), and
  - it can program/console a carrier whose +VIN/+3V3/+1V8 are all OFF.
+5V_DBG is a recognized 5 V rail (power-tree finding: a debug-cable host source,
like usbc_otg's USB_VBUS), not a board source.

### ISOLATION / CONTENTION PROOF (LAW-0) — the SN74LVC125 buffer

The carrier already drives ZYNQ_TCK/TMS/TDI/TDO from the debug_boot 2x7 JTAG
header (a passive connector + TMS/TDI 4k7 insurance pulls) and they reach the
Zynq via the SoM J1 connector. A direct CH347->ZYNQ_T* tie would (a) fight a
JTAG pod on the header, and (b) back-feed the Zynq's JTAG inputs when the carrier
is OFF. U2 (SN74LVC125ADR, quad 3-state buffer, C7661) breaks both:
  - TCK/TDI/TMS pass through three gates whose OUTPUTS drive ZYNQ_TCK/TDI/TMS;
    the fourth gate buffers ZYNQ_TDO back to the CH347 TDO input. Netlist proof
    (extracted): ZYNQ_TCK/TMS/TDI/TDO touch ONLY the buffer pins (U2.3/11/6/9) —
    the CH347 (U1) never touches a Zynq JTAG net. The buffer is a TAP, not a
    short.
  - ALL FOUR OE# pins tie to DBG_JTAG_OE_N: a 100k pull-up to +3V3_DBG holds OE#
    HIGH (outputs Hi-Z) by DEFAULT; SW1 (DSHP04 pos 1) closes OE# to GND to
    ENABLE. So at power-up / cable-just-plugged the buffer is Hi-Z and the header
    pod (or the Zynq) owns JTAG — ZERO contention by default. With the carrier
    OFF + cable plugged + SW1 OPEN, OE# stays high -> no drive onto the unpowered
    Zynq (LVC125 Ioff/partial-power-down keeps a disabled output Hi-Z even with
    the downstream rail at 0 V). A user closes SW1 only to program from the
    bridge with no pod on the header -> exactly one JTAG master at a time.
  - U2 is powered from +3V3_DBG, so an unplugged cable un-powers the buffer ->
    outputs Hi-Z regardless of SW1.

### UART channel B pin allocation (free PL bank)
Console UART1 (TXD1/RXD1) -> a free bank-13 EMIO UART pair:
  - `DBG_UART_RXD` <- IO_L11_SRCC_P_13  (J2.42, ball AA9)
  - `DBG_UART_TXD` <- IO_L11_SRCC_N_13  (J2.40, ball AA8)
bound via `som_conn_gen.FUNCTION_MAP`. Bank 13 = +VCCO_13 = +3V3 = LVCMOS33,
matching the CH347 3.3 V IO (level-safe). PS UART0 was already spent
(uart_bridge, MIO10/11), so the console rides a fabric (EMIO) UART.

### USB front-end (connector sheet)
The USB-C UFP receptacle (TYPE-C-31-M-12 C165948) + the USBLC6-2SC6 D+/D- ESD
(C7519, the carrier-standard low-cap array; SHUNT pass-through 1<->6/3<->4 — no
series element, honouring the CH347 "no series R on UD+/UD-" rule) + the 5.1k Rd
CC pulldowns (UFP/device role) live on `usb_jtag_connector` and publish +5V_DBG
+ DBG_USB_DP/DM (typed usb_hs_pair). See §4 for why this is a separate sheet.

---

## C2 — Pmod expansion port

A single Digilent-standard Pmod host port (2x6, 2.54 mm, 3.3 V): 8 IO + 2x VCC +
2x GND on a right-angle socket (DS1024-2x6R2, the spec-exact part reused from the
existing pmod.py). Row-major Pmod numbering (top 1-6 = IO1-4/GND/VCC, bottom
7-12 = IO5-8/GND/VCC) mapped onto the zigzag connector pads exactly as pmod.py.

### IO pin allocation (8 free bank-13 PL pairs)
All verified free (consumed by NO subsystem; "unclaimed" in the prior XDC):
| Pmod IO | function net | SoM contract | J2 pin | ball |
|---------|--------------|--------------|--------|------|
| IO1 | PMODX_IO1 | IO_L13_MRCC_P_13 | J2.29 | Y6 |
| IO2 | PMODX_IO2 | IO_L13_MRCC_N_13 | J2.27 | Y5 |
| IO3 | PMODX_IO3 | IO_L23_P_13      | J2.33 | V7 |
| IO4 | PMODX_IO4 | IO_L23_N_13      | J2.31 | W7 |
| IO5 | PMODX_IO5 | IO_L14_P_SRCC_13 | J2.41 | AA7 |
| IO6 | PMODX_IO6 | IO_L14_N_SRCC_13 | J2.39 | AA6 |
| IO7 | PMODX_IO7 | IO_L12_MRCC_P_13 | J2.49 | Y9 |
| IO8 | PMODX_IO8 | IO_L12_MRCC_N_13 | J2.47 | Y8 |
bound via `som_conn_gen.FUNCTION_MAP`. Bank 13 = +VCCO_13 = +3V3 = LVCMOS33 (the
carrier already sources this VCCO via VCCO_RAIL_MAP), so the Pmod's 3.3 V level-
safety is STRUCTURAL — no level translation. These eight do not collide with the
existing pmod.py host ports (L2/L3/L4/L5/L7/L8/L9/L10) or user_io. The MRCC/SRCC
clock capability of L12/L13/L14 is preserved (Pmod IO is plain GPIO; the XDC
keeps each create_clock template).

### Power: MANUALLY-GATED rail (constraint C1)
U1 (SY6280AAC) gates +3V3 -> +3V3_PMODX exactly like board_aux / the bring-up
module switches (ILIM = 6800/13k = 523 mA vs the ~100 mA/module Digilent budget),
default-OFF: SW1 (DSHP04 pos 1) closes +3V3 onto EN_PMODX, a 100k pulldown holds
it low until a human flips the switch. So a peripheral whose own 3V3 is down is
never back-fed from this port, and the port is dark at power-up. A status LED on
the gated output shows enable at a glance.

### ESD (cable-facing) + the 200R series DNP option (LAW-0/LAW-1)
Each of the 8 IO carries a low-cap TPD4E1U06 TVS clamp (0.8 pF, C124691) — a pure
GND-referenced SHUNT from the socket-side net (never in series with the signal,
LAW-0). Two TPD4E1U06 (4 ch each) cover the 8 IO. The SoM PL pin lands directly
on the socket pad alongside its clamp (the placer's connector + pure-clamp shunt
idiom — the same topology as the HDMI-RX TMDS / camera FFC ESD).

The Digilent ~200R per-IO series damping resistor is a DOCUMENTED DNP STUFFING
OPTION (the camera / hdmi_rx DNP-reservation idiom), NOT populated on rev A. Why
DNP and not inline: a series resistor between the PL pin and a 3-pin cable net
(socket + clamp) turns that net into a routing TRUNK and leaves the PL-side PORT
as a single-pin strap landing on the trunk — a topology the placer's float-chain
linearizer does not support (it expects the port's series leg to terminate at a
connector "pin", not a trunk). Direct port->{socket, clamp} routes cleanly and is
a valid production Pmod host config; a populated 200R is a BOM-line + pad change
with zero netlist churn if LP/strobe ringing is ever observed.

---

## 4. Why C1 is two sheets (the connector split)

The CH347 bridge sheet alone (CH347 + 8 MHz crystal + LDO + buffer + DIP + mode/
RST pulls) is already busy, and adding the USB-C receptacle + USBLC6 + CC Rd's +
VBUS bulk drove a persistent local routing contention (XI/XO crystal pins 19/20
sit on the same TSSOP edge as UD-/UD+ pins 16/17, and the crystal-cap + USB-ESD-
to-connector routing collide below the part — `DBG_XI vs DBG_UD_M`). Splitting the
receptacle off — the carrier's established "connectors get their own sheet" idiom
(usb_uart_connector is the twin for the CP2102N) — relieves both sheets: each
places cleanly with 0 overlap / 0 crossing. The two bind by +5V_DBG (rail, merges
by name) + DBG_USB_DP/DM (typed ports). So Stream-C adds 3 sheets (usb_jtag,
usb_jtag_connector, pmod_expansion), 30 -> 33.

## 5. Gate status (all green at authoring)
`schgen build` per sheet: NETLIST + ERC + VISUAL all PASS on each of the three.
`schgen board` (full): BOARD GATE PASS (every net merges, root ERC 0); POWER TREE
/ THERMAL / TESTPOINTS / DESIGN RULES / PART RULES / SPICE all PASS; XDC 156 pins
(+10 vs before: 8 Pmod IO + 2 UART), no double-claims. `scripts/check.sh`:
REGRESSION PASS (board + selftest 59/59 mutants killed + m1_rc + pytest 219
passed). The three new renders have NO golden (intentionally NOT blessed).

Author-deferred waivers added: `waive_reset(DBG_RST_N)` (CH347 built-in POR, no
RC by design); `testpoint(+5V_DBG)` on the connector sheet.

## 6. BOM (new parts, all `schgen part add`-generated, live JLC stock 2026-06-15)
| Ref(s) | Part | LCSC | Pkg | Stock | Lib |
|--------|------|------|-----|-------|-----|
| U1 (usb_jtag) | CH347T | C5122332 | TSSOP-20 | 1,953 | Ext |
| U2 (usb_jtag) | SN74LVC125ADR | C7661 | SOIC-14 | 7,330 | Ext |
| U4 (usb_jtag) | AP2112K-3.3TRG1 | C51118 | SOT-25 | 87,465 | Ext |
| Y1 (usb_jtag) | 1C208000BC0R (8 MHz) | C57131 | SMD3225-4P | 32,856 | Ext |
| J1 (connector) | TYPE-C-31-M-12 | C165948 | SMD | 183,962 | Ext |
| U1 (connector) | USBLC6-2SC6 | C7519 | SOT-23-6 | 37,680 | Ext |
| U2/U3 (pmod) | TPD4E1U06DBVR | C124691 | SOT-23-6 | 9,152 | Ext |
| U1 (pmod) | SY6280AAC | (reused) | SOT-23-5 | — | — |
Passives reuse the carrier-standard JLC-Basic values (22p C1653, 100n C1591,
10u C15850, 1u C15849, 10k C25804, 100k C25803, 5.1k C23186, 13k C22797).
