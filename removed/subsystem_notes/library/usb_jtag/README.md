# usb_jtag — CH347T USB-to-JTAG/UART debug bridge (self-powered, isolated)

A project-agnostic, reusable schgen subsystem: a WCH **CH347T** high-speed
USB-to-JTAG + UART bridge that runs as a self-powered debug island. A USB cable
plugged into the project's debug receptacle gives a host PC both a target JTAG
programmer and a console UART (one CH347 channel each, MODE 3) with no external
pod, and it works even when the target's main rails are OFF — the whole bridge
runs off its own debug-USB VBUS and its JTAG IO is buffered so it never
back-feeds an unpowered target. On the Zynq-7000 SoM carrier it is the
on-board programming/console path for the Zynq PL/PS.

## Interface

The subsystem declares its externally-visible nets as ABSTRACT names. Rails
classify as POWER/GROUND by name (the `+` prefix and `GND`), so a standalone
build and a bound build share the same net classes. All internal taps
(`DBG_FT_*`, `DBG_XI/XO`, `DBG_RST_N`, `DBG_MODE_DTR1/RTS1`, `DBG_JTAG_OE_N`)
are private SIGNAL nets and are never part of the interface.

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VBUS_USB`   | POWER  | the debug USB cable's own 5 V VBUS, the U4 LDO input. Alive only while the debug cable is plugged in. Not a target/board rail. |
| `+3V3_ISLAND` | POWER  | the self-powered island 3.3 V rail (U4 output): powers the CH347, the buffer, and every pull. Never depends on a target rail. |
| `GND`         | GROUND | ground. |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `USB_DP`, `USB_DM` | usb_hs_pair | the ESD-protected USB 2.0 HS data pair from the project's debug receptacle. CH347 UD+/UD- take the bus directly (DS forbids a series R); the receptacle + USBLC6 ESD are project-side. |
| `JTAG_TCK`, `JTAG_TDI`, `JTAG_TMS` | single | the three buffered JTAG outputs (SN74LVC125 Y-side) to the target TAP. |
| `JTAG_TDO` | single | the target TDO read back through the fourth buffer gate (a buffer input). |
| `UART_RXD` | single | CH347 TXD1 (pin 3) → target RXD. |
| `UART_TXD` | single | CH347 RXD1 (pin 4) ← target TXD. |

### Binding from a project

A project supplies one standard `META` dict (`schgen.core.subsystem.Meta`) and
forwards it. `bind` rebinds each interface net to a real board net in place and
order-preserving (POWER/GROUND/PORT only; a SIGNAL key or a collision is a hard
`CircuitError`), so binding to the names a hand-written sheet used yields a
byte-identical sheet. `expects` attaches a per-port linker deferral declaring
which project sheet binds a deferred port; `notes` overrides house-style prose
(e.g. the power-tree `draws` note). `meta=None` keeps the abstract names for the
local test.

```python
from subsystems.usb_jtag import usb_jtag

META = {
    "bind": {
        "+VBUS_USB": "+5V_DBG", "+3V3_ISLAND": "+3V3_DBG", "GND": "GND",
        "USB_DP": "MY_USB_DP", "USB_DM": "MY_USB_DM",
        "JTAG_TCK": "MY_TCK", "JTAG_TDI": "MY_TDI",
        "JTAG_TMS": "MY_TMS", "JTAG_TDO": "MY_TDO",
        "UART_RXD": "MY_UART_RXD", "UART_TXD": "MY_UART_TXD",
    },
    "expects": {"USB_DP": "my_debug_usb_connector",
                "JTAG_TCK": "my_jtag_header"},
    "notes": {"draws": "CH347 ~38 mA typ ..."},
}

def circuit():
    return usb_jtag.circuit(META)
```

The carrier adapter is `carrier/subsystems/usb_jtag.py`.

## Design

- **Part choice — CH347T over the FT2232H.** The FT2232H is the canonical
  dual-channel FTDI JTAG+UART bridge, but its 64-pin LQFP is far larger than any
  other carrier IC and the auto-placer cannot route a 64-pin part. The CH347T
  (TSSOP-20) is the direct HS USB-to-JTAG+UART alternative and a standard
  low-cost FPGA/CPU programmer: MODE 3 = "USB to high-speed single serial port +
  USB to JTAG port" (DS §5.2 / §4.6) — exactly a JTAG programmer plus a console
  UART in one. It carries built-in USB termination, config EEPROM, and power-on
  reset, and its side-only TSSOP pins place cleanly.

- **Self-powered island.** U4 (AP2112K-3.3, 600 mA, the carrier's standard LDO
  family) regulates `+3V3_ISLAND` from `+VBUS_USB`, the debug cable's own 5 V
  VBUS — not any target rail. EN is tied to VIN so the bridge is alive whenever
  the cable is plugged, and it can program/console a target whose main rails are
  all OFF. The CH347 is a single 3.3 V supply (DS §5.1/§6.2: 3.0–3.6 V, ICC ~38
  mA typ) on `+3V3_ISLAND.U1.14` with a 100 n decoupling cap.

- **USB.** UD+ (pin 17) / UD- (pin 16) take the protected pair directly; the DS
  forbids a series R and the project-side USBLC6 is a shunt array, so no series
  element is added. The pair is typed `usb_hs_pair` so the SI gate sees the bound
  90 Ω pair.

- **Crystal load caps.** Y1 (KDS `1C208000BC0R`, 8 MHz) is cut for CL = 12 pF, so
  the matched external cap per leg is `Cext = 2·(CL − Cstray) = 2·(12 − ~4) = 16
  pF` C0G on XI(19)/XO(20). The DS-boilerplate ~22 pF assumes a ~20 pF crystal
  and would over-load this part, pulling 8 MHz slow outside the window. The
  crystal's shield/NC pads (Y1.2, Y1.4) tie to GND.

- **RST# — no RC by design.** RST# (pin 1) has the chip's built-in power-on reset
  and an internal pull-up; an external 10 k pull-up to the island rail is added
  for noise immunity only, with no RC cap. A runtime reset is host-/driver-
  mediated over USB, so a `waive_reset` is declared on `DBG_RST_N`.

- **MODE 3 strap.** The CH347 latches its mode from DTR1(10) and RTS1(13) at POR
  (DS §5.2): MODE 3 = both pulled low → one UART + one JTAG TAP. Both pins carry
  internal pull-ups, so the external 10 k pulldowns to GND must dominate (10 k vs
  the ~40 k internal).

- **JTAG isolation / contention guard (LAW-0).** Driving the target JTAG nets
  directly would fight a pod on the target's JTAG header and back-feed the target
  inputs when it is OFF. U2 (SN74LVC125ADR quad 3-state buffer) breaks both: CH347
  TCK(6)/TMS(5)/TDI(8) pass through three gates whose Y outputs drive
  `JTAG_TCK/TMS/TDI`, and a fourth gate buffers `JTAG_TDO` back to CH347 TDO(7).
  All four OE# pins tie to `DBG_JTAG_OE_N`, held HIGH (outputs Hi-Z) by a 100 k
  pull-up to the island rail until a human closes SW1 (DSHP04 pos 1) to pull OE#
  LOW. Default-off and USB-island powered → on power-up the header pod (or the
  target) owns JTAG with zero contention, and exactly one JTAG master is active
  at a time. CH347 TRST (pin 9) is left NC — TRST is optional per the DS §5.6.

- **Console UART.** Channel B is a 2-wire console: TXD1(3) → `UART_RXD`,
  RXD1(4) ← `UART_TXD`.

- **Coverage / budget.** Testpoints on `+3V3_ISLAND`, `UART_TXD`, and `UART_RXD`.
  Power budget: everything rides `+3V3_ISLAND` (U4 sources it from `+VBUS_USB`),
  drawing 0.045 A — CH347 ~38 mA typ plus the buffer and pull network. Unused
  CH347 pins CTS1(2), TRST(9), GPIO/SCL(11), GPIO/SDA(12), ACT/DCD0(15) and the
  three unused SW1 poles (six pins) are explicitly NC.

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| U1 | CH347T | `CH347T` (TSSOP-20, USB→JTAG+UART) | C5122332 |
| U4 | AP2112K-3.3 | `AP2112K-3.3TRG1` (island LDO, 600 mA) | C51118 |
| U2 | SN74LVC125ADR | `SN74LVC125ADR` (quad 3-state buffer, SOIC-14) | C7661 |
| Y1 | 8MHz | `1C208000BC0R` (SMD3225-4P, CL = 12 pF) | C57131 |
| SW1 | DSHP04 | `DSHP04TSGER` (OE# enable switch) | — |
| C (×3) | 100n | `Device:C` (CH347/buffer VCC + LDO out bypass) | C14663 |
| C | 1u | `Device:C` (LDO Cin) | C15849 |
| C | 10u | `Device:C` (LDO Cout bulk) | C15850 |
| C (×2) | 16p | `Device:C` (crystal load, C0G) | C162205 |
| R | 10k | `Device:R` (RST# pull-up) | C25804 |
| R (×2) | 10k | `Device:R` (MODE-3 strap pulldowns) | C25804 |
| R | 100k | `Device:R` (OE# default-HIGH pull-up) | C25803 |

## Build & test

`test_usb_jtag.py` runs the subsystem-local slices offline: declared abstract
interface, model completeness (every pin netted-or-NC), decoupling/STRAP/reset-
waiver design rules, part-rating + per-rail cap-derating coverage (with the
crystal-cap soft exception), the SPICE-subckt ↔ netlist passive match, and the
bind contract (USB-pair payload + testpoint-value rebind). Cross-board gates run
at board level via `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/usb_jtag/test_usb_jtag.py -q
```
