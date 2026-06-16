# usb_jtag_connector — carrier ADAPTER (USB-C UFP debug receptacle)

A **thin carrier adapter** around the project-agnostic reusable subsystem
[`subsystems/usb_jtag_connector/`](../../../subsystems/usb_jtag_connector/README.md).
The portable circuit, SPICE model and local electrical tests all live in that
library; this package is the carrier-specific **glue**: it imports the library
subsystem and **binds** its abstract ports/rails to the carrier's real net
names, reproducing the EXACT net names the hand-written sheet used so the emitted
`carrier/schematic/usb_jtag_connector.kicad_sch` + its golden render stay
**byte-identical**.

Stream-C C1, the connector half (the twin of `usb_uart_connector` for the
CH347T): a USB 2.0 device-role (UFP) USB-C receptacle that supplies the CH347T
USB-JTAG/UART bridge (`usb_jtag`) over a protected data pair + its own 5 V VBUS.

## Package contents

| file | role |
|------|------|
| `usb_jtag_connector.py`      | the ADAPTER — one `META` dict + `circuit()` returning `_lib.circuit(META)` |
| `__init__.py`                | re-exports `circuit` + `META` |
| `usb_jtag_connector.cir`     | carrier-BOUND SPICE subckt (pins = the bound carrier nets); the passive model lives in the generic `.cir` |
| `test_usb_jtag_connector.py` | bind-GUARD test — adapter nets == library bound to `META`, no abstract name leaks |
| `README.md`                  | this file |

The reusable library is the source of truth for the netlist, the active parts
(TYPE-C-31-M-12 receptacle, USBLC6-2SC6 SHUNT ESD array), the device-role Rd
strapping, the USB-2 flip-pair short, the passive values and the abstract
interface contract — see
[`../../../subsystems/usb_jtag_connector/README.md`](../../../subsystems/usb_jtag_connector/README.md).

## The carrier binding (`META`)

`bind` maps each abstract library net -> the carrier real net:

| abstract (library) | carrier net | rationale |
|--------------------|-------------|-----------|
| `+VBUS`       | `+5V_DBG`     | receptacle 5 V VBUS published as +5V_DBG — the bridge's self-powered island source (a POWER rail so it merges onto usb_jtag's AP2112K LDO input; alive only with the cable plugged, constraint C1) |
| `GND`         | `GND`         | identity |
| `CHASSIS_GND` | `CHASSIS_GND` | identity (receptacle shell EH -> chassis) |
| `USB_DP`      | `DBG_USB_DP`  | USB 2.0 HS data pair (90 Ω diff) AFTER the USBLC6-2SC6 ESD array, feeding the CH347T (a SHUNT array, no series R) |
| `USB_DM`      | `DBG_USB_DM`  | USB 2.0 HS data pair |

`expects` — the protected USB pair binds on the `usb_jtag` (CH347T bridge)
sheet, declared as an explicit linker deferral (the exact prior carrier deferral
string) so a standalone link reports the pair as awaiting the bridge, never a
silent open.

`buses`/`notes` — none.

Per-net rationale in full is in the module docstring of `usb_jtag_connector.py`.
