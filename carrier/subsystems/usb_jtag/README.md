# usb_jtag — carrier ADAPTER for the reusable CH347T USB-JTAG/UART subsystem

A **thin carrier adapter**. The portable circuit (netlist + SPICE + README +
local test) lives in the project-agnostic library
[`../../../subsystems/usb_jtag/`](../../../subsystems/usb_jtag/README.md). This
package is the carrier-specific **glue**: it imports that library subsystem and
**binds** its abstract ports/rails to the Zynq carrier's real net names, so the
emitted `carrier/schematic/usb_jtag.kicad_sch` and its golden render are
unchanged. The board build discovers it folder-aware exactly as before
(`circuit()` exposed here).

A USB-C cable plugged at the debug receptacle gives a host PC a Zynq JTAG
programmer AND a console UART (CH347 MODE 3) with no external pod, and it runs
entirely off its OWN debug-USB VBUS / self-powered island so it never back-feeds
an unpowered carrier. The part choice, contention proof, MODE-3 strap and
crystal-load sizing all live in the library README.

## Package contents

| file | role |
|------|------|
| `usb_jtag.py`      | the carrier ADAPTER — `circuit()` + the `META` bind contract (returns `_lib.circuit(META)`) |
| `__init__.py`      | re-exports `circuit`, `META` |
| `usb_jtag.cir`     | thin carrier-BOUND SPICE subckt (pins = carrier nets); passive model lives in `../../../subsystems/usb_jtag/usb_jtag.cir` |
| `test_usb_jtag.py` | offline BIND GUARD — adapter circuit == `lib.circuit(META)`, carrier nets present, no abstract leak |
| `README.md`        | this file |

## The carrier bind (`META`)

`bind` — abstract subsystem net → carrier real net:

| abstract | carrier net | why |
|----------|-------------|-----|
| `+VBUS_USB`   | `+5V_DBG`    | debug-USB receptacle VBUS (LDO input; alive only with the debug cable) |
| `+3V3_ISLAND` | `+3V3_DBG`   | self-powered island rail (AP2112K output) — not a carrier system rail |
| `GND`         | `GND`        | identity |
| `USB_DP`/`USB_DM` | `DBG_USB_DP`/`DBG_USB_DM` | ESD-protected USB 2.0 HS pair from the usb_jtag_connector sheet |
| `JTAG_TCK/TDI/TMS/TDO` | `ZYNQ_TCK/TDI/TMS/TDO` | carrier 2x7 JTAG header (buffered, SW1-gated OE# so no pod contention) |
| `UART_RXD` | `DBG_UART_RXD` | CH347 TXD1 → Zynq RXD |
| `UART_TXD` | `DBG_UART_TXD` | Zynq TXD → CH347 RXD1 |

`expects` — explicit linker deferrals (each port awaits its sheet, never a silent
open):

- USB pair → `usb_jtag_connector` (USB-C UFP receptacle + USBLC6 ESD)
- JTAG ports → `debug_boot` (2x7 JTAG header carries the same `ZYNQ_T*` nets)
- UART ports → `som_j2_connector` (PL bank 13 EMIO UART, LVCMOS33 — FUNCTION_MAP)

`notes` — power-tree draw note (house-style wording, keeps `power_tree.txt`
byte-identical): `CH347 ~38 mA typ (DS) + SN74LVC125 + RST/mode/OE pull network`.

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/usb_jtag/test_usb_jtag.py -q
```

The library's own electrical correctness is proven by
`subsystems/usb_jtag/test_usb_jtag.py`; the board-level gates (power tree, ERC,
link/port-driver graph) stay aggregated by `schgen board`.
