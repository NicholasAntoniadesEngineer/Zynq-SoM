# camera — carrier ADAPTER for the reusable RPi-FFC MIPI CSI-2 camera subsystem

A **thin carrier adapter**. The portable circuit (netlist + SPICE + README +
local test) lives in the project-agnostic library
[`../../../subsystems/camera/`](../../../subsystems/camera/README.md). This
package is the carrier-specific **glue**: it imports that library subsystem and
**binds** its abstract ports/rails to the Zynq carrier's real net names, so the
emitted `carrier/schematic/camera.kicad_sch` and its golden render are unchanged.
The board build discovers it folder-aware exactly as before (`circuit()` exposed
here).

Authored per `carrier/research/camera_csi.md`: SFW15R-1STE1LF 1.0 mm 15P
bottom-contact FFC (LCSC C3168538). The lane map, XAPP894 100R termination
placement and the LP-observability DNP option live in the library README.

## Package contents

| file | role |
|------|------|
| `camera.py`      | the carrier ADAPTER — `circuit()` + the `META` bind contract (returns `_lib.circuit(META)`) |
| `__init__.py`    | re-exports `circuit`, `META` |
| `camera.cir`     | thin carrier-BOUND SPICE subckt (pins = carrier nets); passive model lives in `../../../subsystems/camera/camera.cir` |
| `test_camera.py` | offline BIND GUARD — adapter circuit == `lib.circuit(META)`, carrier nets present, no abstract leak |
| `README.md`      | this file |

## The carrier bind (`META`)

`bind` — abstract subsystem net → carrier real net:

| abstract | carrier net | why |
|----------|-------------|-----|
| `+VDD_CAM` | `+3V3_CAM` | bring-up-gated module rail (SY6280 cell 4); camera-I2C pull-ups tie here so a powered-down camera is not back-fed |
| `GND`      | `GND`      | identity (FFC grounds + mounting tabs) |
| `CSI_D0_P/N`  | `CAM_D0_P/N`  | FFC 3/2 → bank-35 LVDS_25 (+VCCO_35 = 2.5 V) |
| `CSI_D1_P/N`  | `CAM_D1_P/N`  | FFC 6/5 → bank-35 LVDS_25 |
| `CSI_CLK_P/N` | `CAM_CLK_P/N` | FFC 9/8 → bank-35 LVDS_25 |
| `CAM_SCL`/`CAM_SDA` | `CAM_SCL`/`CAM_SDA` | FFC 13/14, dedicated camera I2C (`CAM_I2C` bus, bank 33 3.3 V) — NOT the STM32_I2C2 bus |
| `CAM_EN`  | `CAM_EN`  | FFC 11 module shutdown, bank 33 |
| `CAM_LED` | `CAM_LED` | FFC 12 v1-only indicator, bank 33 |

`expects` — explicit linker deferrals (each port awaits the generated J3 sheet,
never a silent open):

- CSI lanes → `som_j3_connector` (PL bank 35, LVDS_25, +VCCO_35 = 2.5 V)
- control I2C + EN/LED → `som_j3_connector` (PL bank 33, +VCCO_33 = 3.3 V)

`buses` — `{"i2c": "CAM_I2C"}` (the dedicated camera I2C bus; keeps the derived
`layout_constraints.csv` bus grouping byte-identical).

`notes` — power-tree draw note (cites the carrier dossier wording, keeps
`power_tree.txt` byte-identical): `RPi camera module budget (camera_csi.md: V2
typ ~250 mA)`.

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/camera/test_camera.py -q
```

The library's own electrical correctness is proven by
`subsystems/camera/test_camera.py`; the board-level gates (power tree, ERC,
link/port-driver graph) stay aggregated by `schgen board`.
