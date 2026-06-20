# som_j1 — SoM mezzanine connector J1 (carrier-local subsystem)

The carrier side of the **J1** Hirose **DF40C-100DP-0.4V(51)** mezzanine
receptacle that mates the Zynq-7000 SoM to this carrier. J1 carries the
**power / USB / STM32-SC / JTAG / SDIO / Ethernet-MDI** half of the contract.

This is a **carrier-LOCAL** subsystem, not a project-agnostic library package: it
is bound to the SoM by construction (every pin is the SoM side of the contract).
It is foldered into a per-name package — `som_j1.py` (netlist), `__init__.py`
(re-export), `README.md`, `test_som_j1.py`, `som_j1.cir` — to give it the same
4-artifact parity as the generic `subsystems/<name>/` library.

## How it is generated (never hand-typed)

`som_j1.py` is a thin wrapper: it loads the shared generator
`carrier/som_conn_gen.py` and calls
`connector_circuit("J1", "som_j1", "SoM J1: power / USB / STM32 / JTAG / SDIO / ETH MDI")`.
The pin→net map comes from `carrier/som_interface.json` (extracted from the SoM
KiCad project by `schgen som-interface`); the generator binds **every** J1 pin
to its contract net VERBATIM, applies the wave-3 function/rail rebinds, types the
diff pairs, and declares the module power draw. Regenerate the contract after any
SoM change and this sheet follows — there is no hand-typed pinout.

## Package contents

| file | role |
|------|------|
| `som_j1.py`       | the NETLIST — `circuit()` instantiating the DF40 receptacle bound to the J1 contract |
| `__init__.py`     | re-exports `circuit` |
| `som_j1.cir`      | SPICE subckt stub — externally-visible nets as pins; a pure connector carries no on-sheet passive network |
| `test_som_j1.py`  | LOCAL correctness test (offline: model completeness + design-rule slice + sheet invariants) |
| `README.md`       | this file |

## The connector — part

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J1 | DF40C-100DP-0.4V(51) | `parts/DF40C-100DP-0.4V_51/` (100 bare-number pins) | C531031 |

## Interface it carries (the J1 contract)

### Rails (POWER / GROUND)

| net | class | source / note |
|-----|-------|---------------|
| `+5V_SOM`  | POWER  | SoM module input on J1.1-14. **P0 rebind**: the SoM net `VIN` is the module's 4.2-5 V input and is bound to the carrier always-on **+5V_SOM** buck (power.py), NOT the 20 V PD rail — binding 20 V here destroys the SoM (wave3_function_map.md P0). Declared draw: 2.0 A (~10 W class, estimate). |
| `+3V3_SC`  | POWER  | SoM system-controller 3.3 V domain pins. |
| `GND`      | GROUND | ground. |

### Isolated SoM rails — explicit no-connects (round-5 rail isolation)

The SoM exports its own `+3V3` (J1.24-27) and `+1V8` (J1.56/58/60) from on-module
MPM3834 stages, while the carrier regulates same-named rails from its own bucks.
Binding these pins would parallel two regulators on one net, so they are emitted
as **explicit author no-connects** — never silently dropped:

| pins | SoM rail | why NC |
|------|----------|--------|
| J1.24, J1.25, J1.26, J1.27 | `+3V3` | carrier TPS54302 (power:U2) is the only +3V3 source |
| J1.56, J1.58, J1.60        | `+1V8` | carrier AP2112K (power:U3) is the only +1V8 source |

### Signal ports (PORT, 58 total)

Highlights (consumer sheet binds the same name):

- **Ethernet MDI** — `ETH_PHY_MDI{0..3}_{P,N}` (typed `diff_pair` 100R), `ETH_LED1`, `ETH_LED2`.
- **USB** — `STM32_USB_D_{P,N}` and `USB_D+`/`USB_D-` (typed `usb_hs_pair` 90R), `STM32_USB_CC1/CC2`, `USB_ID`, `USB_VBUS`, `VBUS_OUT_EN`.
- **STM32 SC** — rail-EN override vetoes `STM32_RAIL_EN_{5V0,3V3,1V8}`, shared open-drain interrupt `SC_INT_N`, bit-banged `STM32_I2C2_{SDA,SCL}` (on the DAC pins), `STM32_NRST`, `STM32_BOOT0`, `STM32_GPIO5..8`.
- **JTAG** — `ZYNQ_TCK/TDI/TDO/TMS`.
- **SDIO** — `SDIO_CLK/CMD/D0..D3`, typed `sd_bus` at **1.8 V** (the SoM runs SDIO at 1.8 V straight into the Zynq; the carrier microSD subsystem must level-translate).
- **PS** — `ZYNQ_PS_UART0_{RXD,TXD}`, plain MIO spares `ZYNQ_PS_MIO0/9/12`, and the MIO voltage-mode straps `ZYNQ_PS_MIO7/VM0` + `ZYNQ_PS_MIO8\VM1` (DO-NOT-LOAD — strapped on the SoM).
- **FMC** — `FMC_LA08..11_{P,N}` (typed `diff_pair` 100R).

## Notes

- **Connector-only sheet**: the netlist adds no discretes (no decoupling, no
  straps) — the placement engine's connector-fan template fires only for a lone
  ≥40-pin part, so any carrier-side strap (e.g. PUDC) lives on another sheet.
- The diff-pair / SD-bus typing is applied here so the constraints exporter sees
  both ends of every pair on this sheet.
- Byte-identical: foldering this subsystem changed no emitted schematic or render.
