# usb_jtag — CH347T USB-JTAG/UART debug bridge (reusable subsystem)

A project-agnostic, self-contained schgen subsystem: a **WCH CH347T** HS
USB-to-JTAG + UART bridge running as a **self-powered, isolated** debug island.
A USB cable plugged into the project's debug receptacle gives a host PC a target
JTAG programmer **and** a console UART (one CH347 channel each, MODE 3) with no
external pod — and it works even when the target's main rails are OFF, because
the whole bridge runs off its own debug-USB VBUS and its JTAG IO is buffered so
it never back-feeds an unpowered target. It declares its interface as
**abstract** port + rail names and knows nothing about any board; a consuming
project supplies a **bind map** (`abstract -> real net`) to drop it onto real
nets.

## Package contents

| file | role |
|------|------|
| `usb_jtag.py`      | the NETLIST — `circuit(meta=None)`, abstract ports/rails |
| `usb_jtag.cir`     | SPICE subckt — the passive network with the abstract rails as subckt pins |
| `test_usb_jtag.py` | LOCAL electrical-correctness test (offline, runs the board gate slices on just this subsystem) |
| `README.md`        | this file |

Active parts are **referenced, never vendored**: the CH347T / AP2112K / SN74LVC125 /
crystal / DIP-switch symbols/footprints/LCSC come from the global `parts/` lib.
No `lib_id` override is used — the faithful dossier symbols are drawn directly
(the "0 hand-built symbols" law).

## The abstract interface (the reuse contract)

A consuming project binds these names. Rails classify as POWER/GROUND by name
(the `+` prefix + `GND`), exactly as real board rails do, so a standalone build
and a bound build share net classes.

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VBUS_USB`   | POWER  | the debug USB cable's **own** 5 V VBUS, the LDO (U4) input. Alive **only** while the debug cable is plugged → the whole bridge is too. **Not** a target/board rail. |
| `+3V3_ISLAND` | POWER  | the self-powered island 3.3 V rail (U4 output): powers the CH347, the buffer and all the pulls. A project names this its local LDO-output net; it never depends on a target rail. |
| `GND`         | GROUND | ground. |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `USB_DP`, `USB_DM`      | usb_hs_pair | the ESD-protected USB 2.0 HS data pair from the project's debug receptacle. The CH347 UD+/UD- take the bus **directly** (DS forbids a series R); the receptacle + USBLC6 ESD are project-side. |
| `JTAG_TCK`, `JTAG_TDI`, `JTAG_TMS` | single | the three **buffered** JTAG outputs (SN74LVC125 Y-side) to the target TAP. |
| `JTAG_TDO`              | single | the target TDO read back through the fourth buffer gate (a buffer **input**). |
| `UART_RXD`              | single | bridge UART RXD-side line — CH347 **TXD1** (pin 3) → target RXD. |
| `UART_TXD`              | single | bridge UART TXD-side line — CH347 **RXD1** (pin 4) ← target TXD. |

The four CH347 JTAG taps (`DBG_FT_*`), the crystal nodes (`DBG_XI/XO`), the RST#
node (`DBG_RST_N`), the two MODE-strap nodes (`DBG_MODE_DTR1/RTS1`) and the OE#
node (`DBG_JTAG_OE_N`) are the subsystem's **private internal SIGNAL nets** — they
are kept verbatim and are never part of the abstract interface.

### Parts (from the global `parts/` lib + inline passives)

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| U1 | CH347T | `parts/CH347T/` (TSSOP-20, USB→JTAG+UART) | C5122332 |
| U4 | AP2112K-3.3 | `parts/AP2112K-3.3TRG1/` (island LDO) | C51118 |
| U2 | SN74LVC125ADR | `parts/SN74LVC125ADR/` (quad 3-state buffer) | C7661 |
| Y1 | 8 MHz | `parts/1C208000BC0R/` (CL=12 pF crystal) | C57131 |
| SW1 | DSHP04 | `parts/DSHP04TSGER/` (OE# enable switch) | — |
| C (×3) | 100n | `Device:C` (CH347/buffer VCC + LDO out bypass) | C14663 |
| C | 1u | `Device:C` (LDO Cin) | C15849 |
| C | 10u | `Device:C` (LDO Cout bulk) | C15850 |
| C (×2) | 16p | `Device:C` (crystal load, C0G) | C162205 |
| R | 10k | `Device:R` (RST# pull-up) | C25804 |
| R (×2) | 10k | `Device:R` (MODE-3 strap pulldowns) | C25804 |
| R | 100k | `Device:R` (OE# default-HIGH pull-up) | C25803 |

## Consuming it from a project

A project supplies a thin adapter declaring ONE standard `META` dict (the
adapter contract, `schgen.core.subsystem.Meta`) and forwards it:

```python
from subsystems.usb_jtag import usb_jtag

META = {
    # abstract subsystem net -> your real board net
    "bind": {
        "+VBUS_USB": "+5V_DBG", "+3V3_ISLAND": "+3V3_DBG", "GND": "GND",
        "USB_DP": "MY_USB_DP", "USB_DM": "MY_USB_DM",
        "JTAG_TCK": "MY_TCK", "JTAG_TDI": "MY_TDI",
        "JTAG_TMS": "MY_TMS", "JTAG_TDO": "MY_TDO",
        "UART_RXD": "MY_UART_RXD", "UART_TXD": "MY_UART_TXD",
    },
    # optional: tell the linker which of your sheets will bind a deferred port
    "expects": {"USB_DP": "my_debug_usb_connector",
                "JTAG_TCK": "my_jtag_header", ...},
    # optional house-style override (keep your power-tree note byte-stable)
    "notes": {"draws": "CH347 ~38 mA typ ..."},
}

def circuit():
    return usb_jtag.circuit(META)
```

The four standard `META` keys (`bind` / `expects` / `buses` / `notes`) are
universal across every reusable subsystem — a typo'd top-level key is a hard
`CircuitError`, never silently dropped. `bind` renames every external **in
place, order-preserving** (POWER/GROUND/PORT only — a SIGNAL net is private
wiring and is never rebound; a SIGNAL key or a collision is a hard
`CircuitError`). Because the rename preserves net insertion order, parts, refs,
NCs, the USB-pair `pair_with` payload and the testpoint values, **binding to the
exact names a hand-written sheet used yields a byte-identical emitted sheet.**
The carrier adapter is `carrier/subsystems/usb_jtag.py`.

## Design notes (datasheet + bring-up contract)

- **Self-powered island.** The whole bridge runs off `+3V3_ISLAND`, which U4
  (AP2112K) regulates from `+VBUS_USB` — the debug cable's own 5 V VBUS, **not**
  any target rail. So the bridge is alive only while the debug cable is plugged
  in, and it can program / console a target whose rails are all OFF.
- **MODE 3 strap.** The CH347 latches its mode from DTR1(10)/RTS1(13) at POR (DS
  §5.2): MODE 3 = both pulled low → one UART + one JTAG TAP. Both pins have
  internal pull-ups, so the external 10k pulldowns must dominate (10k vs ~40k).
- **JTAG isolation / contention guard (LAW-0).** The three CH347 JTAG outputs
  pass through SN74LVC125 buffer gates to `JTAG_TCK/TDI/TMS`; a fourth gate
  buffers `JTAG_TDO` back. All four OE# pins tie to `DBG_JTAG_OE_N`, held HIGH by
  a 100k pull-up to the island rail (outputs Hi-Z) until a human closes SW1
  (DSHP04 pos 1) to pull OE# LOW. Default-off + USB-island power → exactly one
  JTAG master at a time; never a hard short onto the target TAP. TRST is left NC
  (OPTIONAL per the CH347 DS §5.6).
- **Crystal load caps.** Y1 (KDS `1C208000BC0R`) is cut for CL=12 pF, so the
  matched external cap per leg is `Cext = 2·(CL − Cstray) = 2·(12 − ~4) = 16 pF`
  C0G — **not** the DS-boilerplate ~22 pF (22 pF would over-load it and pull
  8 MHz slow, outside the ±20 ppm window). LCSC C162205 has no ratings-catalog
  row; the board's `part_rules` reports this as a **soft** note (not a hard
  finding), and the local test mirrors that exact soft treatment.
- **RST# / no RC by design.** `DBG_RST_N` (CH347 RST#) is defined-high with a 10k
  pull-up only — the CH347 has a built-in power-on reset and RST# carries its own
  internal pull-up; the external 10k is noise-immunity insurance. A runtime reset
  is host-/driver-mediated over USB, not an RC ramp → a `waive_reset` is declared.

## Local test vs board gates

`test_usb_jtag.py` runs the **subsystem-local** slices offline: declared abstract
interface, model completeness (every pin netted-or-NC), decoupling completeness
(design_rules DECAP/EP/STRAP + the RST# waiver), part-rating coverage + per-rail
cap derating (with the documented crystal-cap soft exception), the SPICE-subckt ↔
netlist passive match (caps **and** resistors), and the bind contract (incl. the
USB-pair payload + testpoint-value rebind). **Cross-board** gates stay aggregated
at board level and are *not* duplicated here: the link / port-driver graph, the
full power-tree headroom, the SI length-match emission, board ERC and the board
netlist merge — all run by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/usb_jtag/test_usb_jtag.py -q
```
