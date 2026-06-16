# usbc_otg — carrier ADAPTER (USB 2.0 HS OTG port, bound to the Zynq carrier)

A **thin carrier adapter** around the project-agnostic reusable subsystem
[`subsystems/usbc_otg/`](../../../subsystems/usbc_otg/README.md). The portable
circuit, SPICE model and local electrical tests all live in that library; this
package is the carrier-specific **glue**: it imports the library subsystem and
**binds** its abstract ports/rails to the carrier's real net names, reproducing
the EXACT net names the hand-written sheet used so the emitted
`carrier/schematic/usbc_otg.kicad_sch` + its golden render stay
**byte-identical**.

## Package contents

| file | role |
|------|------|
| `usbc_otg.py`      | the ADAPTER — one `META` dict + `circuit()` returning `_lib.circuit(META)` |
| `__init__.py`      | re-exports `circuit` + `META` |
| `usbc_otg.cir`     | carrier-BOUND SPICE subckt (pins = the bound carrier nets); the passive model lives in the generic `.cir` |
| `test_usbc_otg.py` | bind-GUARD test — adapter nets == library bound to `META`, no abstract name leaks |
| `README.md`        | this file |

The reusable library is the source of truth for the netlist, the active parts
(TYPE-C-31-M-12 receptacle, TPS2051C current-limited switch, USBLC6-2SC6 ESD
array), the passive values and the abstract interface contract — see
[`../../../subsystems/usbc_otg/README.md`](../../../subsystems/usbc_otg/README.md).

## The carrier binding (`META`)

`bind` maps each abstract library net -> the carrier real net:

| abstract (library) | carrier net | rationale |
|--------------------|-------------|-----------|
| `+VBUS_SUPPLY` | `+5V_USB`      | bring-up-gated module rail (SY6280); the port sources it onto cable VBUS via the TPS2051C |
| `+VDD_LOGIC`   | `+3V3_SC`      | SC rail; G4 abs-max fix — FLT# pull-up re-railed off +5V_USB so FLT# stays readable with the module rail gated OFF |
| `GND`          | `GND`          | identity |
| `CHASSIS_GND`  | `CHASSIS_GND`  | identity (receptacle shell/shield bond) |
| `USB_DP`       | `USB_D+`       | SoM USB HS PHY data pair (90 Ω diff) |
| `USB_DM`       | `USB_D-`       | SoM USB HS PHY data pair |
| `VBUS`         | `USB_VBUS`     | connector VBUS the SoM senses (TPS2051 OUT + receptacle pads + CC Rp ref + ESD VBUS pin) |
| `VBUS_EN`      | `VBUS_OUT_EN`  | SoM VBUS-source enable (contract J1.38) |
| `FLT_N`        | `USBOTG_FLT_N` | open-drain fault flag, read by the SC via TCA9535 expander P14 (bringup_rails) |
| `USB_ID`       | `USB_ID`       | identity; OTG ID (contract J1.20) strapped low through 1k = HOST role |

`expects` — `VBUS_EN`/`USB_ID` bind on the generated J1 sheet (`som_conn_gen`
FUNCTION_MAP) and `FLT_N` binds on the bringup sheet (TCA9535 port P14);
declared as explicit linker deferrals so a standalone link reports them as
awaiting their off-sheet binder, never a silent open.

`notes` — the power-tree draw notes (downstream USB device budget,
TPS2051C current-limited; USBOTG_FLT# 100k pull-up under the G4 re-rail) keep the
carrier's derived `power_tree.txt` byte-identical to the hand-written sheet.

Per-net rationale in full is in the module docstring of `usbc_otg.py`.
