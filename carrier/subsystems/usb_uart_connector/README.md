# usb_uart_connector — carrier ADAPTER (USB-C UFP console receptacle)

A **thin carrier adapter** around the project-agnostic reusable subsystem
[`subsystems/usb_uart_connector/`](../../../subsystems/usb_uart_connector/README.md).
The portable circuit, SPICE model and local electrical tests all live in that
library; this package is the carrier-specific **glue**: it imports the library
subsystem and **binds** its abstract ports/rails to the carrier's real net
names, reproducing the EXACT net names the hand-written sheet used so the emitted
`carrier/schematic/usb_uart_connector.kicad_sch` + its golden render stay
**byte-identical**.

Wave-2 external console port: a USB 2.0 device-role (UFP) USB-C receptacle that
supplies the CP2102N USB-UART bridge (`uart_bridge`) over a protected data pair.

## Package contents

| file | role |
|------|------|
| `usb_uart_connector.py`      | the ADAPTER — one `META` dict + `circuit()` returning `_lib.circuit(META)` |
| `__init__.py`                | re-exports `circuit` + `META` |
| `usb_uart_connector.cir`     | carrier-BOUND SPICE subckt (pins = the bound carrier nets); the passive model lives in the generic `.cir` |
| `test_usb_uart_connector.py` | bind-GUARD test — adapter nets == library bound to `META`, no abstract name leaks |
| `README.md`                  | this file |

The reusable library is the source of truth for the netlist, the active parts
(TYPE-C-31-M-12 receptacle, USBLC6-2SC6 ESD array), the device-role 5.1k Rd CC
pulldowns, the passive values and the abstract interface contract — see
[`../../../subsystems/usb_uart_connector/README.md`](../../../subsystems/usb_uart_connector/README.md).

## The carrier binding (`META`)

`bind` maps each abstract library net -> the carrier real net:

| abstract (library) | carrier net | rationale |
|--------------------|-------------|-----------|
| `GND`         | `GND`            | identity |
| `CHASSIS_GND` | `CHASSIS_GND`    | identity (receptacle shell/shield bond) |
| `VBUS`        | `USB_UART_VBUS`  | receptacle 5 V VBUS (the bridge senses it through its own divider — self-powered cable-attach); NOT a board input rail |
| `USB_DP`      | `USB_UART_DP`    | USB 2.0 HS data pair (90 Ω diff), behind the ESD array; the bridge's USB pins join here |
| `USB_DM`      | `USB_UART_DM`    | USB 2.0 HS data pair |

The `VBUS`/`USB_DP`/`USB_DM` carrier net names are the EXACT names the
`uart_bridge` peer binds for its USB side (the bridge declares
`expect="usb_uart_connector (wave 2)"` on them), so the two sheets join those
nets at link time.

`expects`/`buses`/`notes` — none. The connector **produces** these nets (the
bridge defers TO it), the original sheet carried no port deferral, and a
UFP/device port sinks rather than sources VBUS so it adds no power-tree draw —
matching the hand-written sheet byte-for-byte.

Per-net rationale in full is in the module docstring of `usb_uart_connector.py`.
