# usb_pd — carrier ADAPTER (FUSB302B USB-PD sink, bound to the Zynq carrier)

A **thin carrier adapter** around the project-agnostic reusable subsystem
[`subsystems/usb_pd/`](../../../subsystems/usb_pd/README.md). The portable
circuit, SPICE model and local electrical tests all live in that library; this
package is the carrier-specific **glue**: it imports the library subsystem and
**binds** its abstract ports/rails to the carrier's real net names, reproducing
the EXACT net names the hand-written sheet used so the emitted
`carrier/schematic/usb_pd.kicad_sch` + its golden render stay **byte-identical**.

## Package contents

| file | role |
|------|------|
| `usb_pd.py`      | the ADAPTER — one `META` dict + `circuit()` returning `_lib.circuit(META)` |
| `__init__.py`    | re-exports `circuit` + `META` (some tests import `META` from the package) |
| `usb_pd.cir`     | carrier-BOUND SPICE subckt (pins = the bound carrier nets); the passive model lives in the generic `.cir` |
| `test_usb_pd.py` | bind-GUARD test — adapter nets == library bound to `META`, no abstract name leaks |
| `README.md`      | this file |

The reusable library is the source of truth for the netlist, the active part
(`Interface_USB:FUSB302BMPX` from `parts/`), the passive values and the abstract
interface contract — see [`../../../subsystems/usb_pd/README.md`](../../../subsystems/usb_pd/README.md).

## The carrier binding (`META`)

`bind` maps each abstract library net -> the carrier real net:

| abstract (library) | carrier net | rationale |
|--------------------|-------------|-----------|
| `+VDD_LOGIC`  | `+3V3_SC`        | FUSB302B VDD/INT on the always-on SoM SC rail — PD negotiation runs **before** any DIP-gated carrier rail exists (bring-up risk R1) |
| `+VBUS_SENSE` | `+VBUS_IN`       | raw receptacle VBUS **ahead of** the TPS26631 inlet eFuse, so the PHY observes vSafe5V/vbus at the connector for attach detection |
| `GND`         | `GND`            | identity |
| `CC1`         | `STM32_USB_CC1`  | receptacle CC1 (pd_input J1); the FUSB302B OWNS CC (firmware contract PD-CC-1: SoM UCPD stays Hi-Z) |
| `CC2`         | `STM32_USB_CC2`  | receptacle CC2 |
| `I2C_SDA`     | `STM32_I2C2_SDA` | shared STM32_I2C2 bus; pull-ups live ONCE on bringup_rails |
| `I2C_SCL`     | `STM32_I2C2_SCL` | shared STM32_I2C2 bus |
| `INT_N`       | `SC_INT_N`       | G2 wire-OR onto the single shared SC interrupt; one 10k pull on bringup_rails |

`expects` — `I2C_SDA`, `I2C_SCL`, `INT_N` bind on the generated J1 sheet
(`som_conn_gen` FUNCTION_MAP), declared as explicit linker deferrals so a
standalone link reports them as awaiting-J1, never a silent open.

`buses` — `{"i2c": "STM32_I2C2"}` (the FUSB302 I2C sits on the carrier STM32_I2C2 bus).

`notes` — the power-tree draw note (FUSB302B VDD < 1 mA; SC_INT_N pulled on
bringup_rails) keeps the carrier's derived `power_tree.txt` / layout-constraint
artifacts byte-identical to the hand-written sheet.

Per-net rationale in full is in the module docstring of `usb_pd.py`.
