# uart_bridge — carrier ADAPTER for the reusable CP2102N USB-UART subsystem

A **thin carrier adapter**. The portable circuit (netlist + SPICE + README +
local test) lives in the project-agnostic library
[`../../../subsystems/uart_bridge/`](../../../subsystems/uart_bridge/README.md).
This package is the carrier-specific **glue**: it imports that library subsystem
and **binds** its abstract ports/rails to the Zynq carrier's real net names
(including the UART null-modem crossover, which lives in the bind map), so the
emitted `carrier/schematic/uart_bridge.kicad_sch` and its golden render are
unchanged. The board build discovers it folder-aware exactly as before
(`circuit()` exposed here).

The CP2102N is self-powered off the carrier `+3V3` rail; the console UART crosses
over to the Zynq PS UART0. The part choice and self-powered decoupling live in
the library README.

## Package contents

| file | role |
|------|------|
| `uart_bridge.py`      | the carrier ADAPTER — `circuit()` + the `META` bind contract (returns `_lib.circuit(META)`) |
| `__init__.py`         | re-exports `circuit`, `META` |
| `uart_bridge.cir`     | thin carrier-BOUND SPICE subckt (pins = carrier nets); passive model lives in `../../../subsystems/uart_bridge/uart_bridge.cir` |
| `test_uart_bridge.py` | offline BIND GUARD — adapter circuit == `lib.circuit(META)`, carrier nets present, no abstract leak |
| `README.md`           | this file |

## The carrier bind (`META`)

`bind` — abstract subsystem net → carrier real net:

| abstract | carrier net | why |
|----------|-------------|-----|
| `+VDD_IO`  | `+3V3`            | CP2102N self-powered: VREGIN + VDD + VIO + the 1k ~RST pull-up all sit on +3V3 |
| `GND`      | `GND`             | identity |
| `USB_VBUS` | `USB_UART_VBUS`   | the USB-UART receptacle's OWN 5 V VBUS (cable-attach detect) — NOT a board input rail |
| `USB_DP`/`USB_DM` | `USB_UART_DP`/`USB_UART_DM` | receptacle USB 2.0 HS pair (90R diff) |
| `UART_TXD`   | `ZYNQ_PS_UART0_RXD` | bridge TXD → Zynq RXD (null-modem crossover) |
| `UART_RXD`   | `ZYNQ_PS_UART0_TXD` | Zynq TXD → bridge RXD |
| `UART_RTS_N` | `ZYNQ_PS_UART0_CTS_N` | bridge ~RTS → Zynq ~CTS |
| `UART_CTS_N` | `ZYNQ_PS_UART0_RTS_N` | Zynq ~RTS → bridge ~CTS |

`expects` — explicit linker deferrals (each port awaits its sheet, never a silent
open):

- USB ports → `usb_uart_connector` (wave-2 USB-UART receptacle sheet)
- UART ports → `som_j1_connector` (wave-3 MIO→UART0 function map)

`notes` — power-tree draw note (house-style wording, keeps `power_tree.txt`
byte-identical): `CP2102N active ~14 mA typ + RST 1k pull-up`.

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/uart_bridge/test_uart_bridge.py -q
```

The library's own electrical correctness is proven by
`subsystems/uart_bridge/test_uart_bridge.py`; the board-level gates (power tree,
ERC, link/port-driver graph) stay aggregated by `schgen board`.
