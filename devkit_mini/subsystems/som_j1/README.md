# som_j1 — SoM mezzanine connector J1 (power / USB / STM32-SC / JTAG / SDIO / ETH-MDI)

`som_j1` is the carrier side of the **J1** Hirose DF40 mezzanine connector that
mates the Zynq-7000 SoM to this carrier. J1 carries the power, USB 2.0,
STM32 system-controller, JTAG, SDIO and Ethernet-MDI half of the SoM↔carrier
contract. It is a carrier-LOCAL subsystem (bound to the SoM by construction),
emitted entirely from the contract — there is no hand-typed pinout.

## Interface

`som_j1.py` is a thin wrapper: it loads the shared generator
`devkit_mini/som_conn_gen.py` and calls
`connector_circuit("J1", "som_j1", "SoM J1: power / USB / STM32 / JTAG / SDIO / ETH MDI")`.
The pin→net map for J1's 100 signal pins comes from `devkit_mini/som_interface.json`
(extracted from the SoM KiCad project by `schgen som-interface`). The generator
binds every J1 pin to its carrier net via `resolve_net()` and exposes those nets
to the rest of the carrier; consumer sheets (ethernet, usb_pd, uart_bridge, fmc,
…) bind to the same net names from their own sheets.

Nets J1 drives:

- **Rails (POWER/GROUND):** `+5V_SOM` (J1.1-14), `+3V3_SC` (J1.37), `GND` (20 pins).
- **Ethernet MDI (PORT, typed):** `ETH_PHY_MDI{0..3}_{P,N}` (100R `diff_pair`),
  `ETH_LED1`, `ETH_LED2`.
- **USB (PORT, typed):** `STM32_USB_D_{P,N}` and `USB_D+`/`USB_D-`
  (90R `usb_hs_pair`), `STM32_USB_CC1/CC2`, `USB_ID`, `USB_VBUS`, `VBUS_OUT_EN`.
- **STM32 SC (PORT):** `STM32_RAIL_EN_{5V0,3V3,1V8}` (rail-EN override vetoes),
  `SC_INT_N` (shared open-drain interrupt), `STM32_I2C2_{SDA,SCL}` (bit-banged on
  the DAC pins), `STM32_NRST`, `STM32_BOOT0`, `STM32_GPIO5..8`.
- **JTAG (PORT):** `ZYNQ_TCK/TDI/TDO/TMS`.
- **SDIO (PORT, typed):** `SDIO_CLK/CMD/D0..D3`, typed `sd_bus` at 1.8 V.
- **PS (PORT):** `ZYNQ_PS_UART0_{RXD,TXD}` (MIO10/11), spare MIO `ZYNQ_PS_MIO0/9/12`,
  and the voltage-mode straps `ZYNQ_PS_MIO7/VM0` + `ZYNQ_PS_MIO8\VM1` (DO-NOT-LOAD).
- **FMC (PORT, typed):** `FMC_LA08..11_{P,N}` (100R `diff_pair`).

Explicit author no-connects on J1: the SoM's on-module `+3V3` (J1.24-27) and
`+1V8` (J1.56/58/60) rail pins, plus the plug's 4 hold-down pads (101-104).

## Design

- **Connector part — DF40C-100DP-0.4V(51), the PLUG (DP).** The SoM is built
  with the DF40 DS receptacle on J1/J2/J3; DF40 mates only DP-plug ↔ DS-receptacle,
  so the carrier (the schgen-controlled side) carries the plug. Two receptacles
  would never interlock. Signal pins 1-100 keep the same contract net→pad-number
  map (the Hirose DP/DS pair mates pad-N ↔ pad-N by design); pads 101-104 are
  mechanical hold-down nails and are no-connects.

- **`VIN` → `+5V_SOM` rail rebind.** The SoM `VIN` net (J1.1-14) is the module's
  4.2-5 V input, NOT the 20 V PD rail. It is bound to the carrier always-on
  `+5V_SOM` buck (power_som U4, a 6 A LM61460). Binding the 20 V `+VIN` rail here
  would destroy the SoM. `REBOUND_SOM_RAILS` holds this map and the linker
  errors if it drifts from its policy twin in `schgen.link`. The carrier 20 V
  `+VIN` rail is a separate net that does not reach the SoM connector.

- **Isolated SoM rails — carrier bucks win.** The SoM exports its own `+3V3`
  (J1.24-27) and `+1V8` (J1.56/58/60) from on-module MPM3834 stages, while the
  carrier regulates same-named rails from its own LM61460 (power U2) and AP2112K
  (power U3). Binding these pins would parallel two regulators on one net, so they
  are emitted as explicit per-pin KiCad no-connects (never silently dropped);
  `ISOLATED_SOM_RAILS` is the policy twin and the per-sheet netlist gate proves
  every one.

- **STM32 I2C2 bit-banged on the DAC pins.** PA4/PA5 (`STM32_DAC1/2`, J1.49/55)
  have no I2C alternate function — the real I2C2 (PA8/PA9) is consumed on-module
  as the SC↔Zynq link — so the carrier I2C2 (`STM32_I2C2_SDA/SCL`) is firmware
  bit-banged on these GPIOs; the DAC analog outputs are sacrificed (no carrier
  subsystem ever claimed them).

- **`SC_INT_N` two-consumer merge.** `STM32_GPIO4` (PA15, J1.41) is the shared
  open-drain SC interrupt — a wire-OR of the TCA9535 INT# (bringup_rails) and the
  FUSB302 INT (usb_pd). Both consumers carry an `SC_INT_N` port; the linker
  accepts the multi-consumer merge.

- **MIO voltage-mode straps are DO-NOT-LOAD.** `ZYNQ_PS_MIO7/VM0` (J1.40) and
  `ZYNQ_PS_MIO8\VM1` (J1.36) are the Zynq PS-bank MIO voltage-mode select straps,
  sampled at POR and strapped on the SoM. They are exposed verbatim for probe
  visibility only; no carrier pull, driver, or consumer may be added or it would
  fight the SoM strap and mis-set the MIO bank voltage at boot.

- **SDIO at 1.8 V.** `SDIO_CLK/CMD/D0..D3` are typed `sd_bus(level_v=1.8)` — the
  SoM runs SDIO at 1.8 V straight into the Zynq, so the carrier microSD subsystem
  must level-translate.

- **Differential-pair typing on-sheet.** The Ethernet MDI pairs (100R), the two
  USB 2.0 pairs (90R) and the FMC LA08-11 pairs (100R) are typed here (applied
  only when both ends are present on J1) so the constraints exporter sees both
  ends of every pair on this sheet.

- **Power budget.** J1 declares a `+5V_SOM` draw of 2.15 A — the SoM module
  (Zynq + DDR3L + PHYs, ~10 W class) at the regulated 4.65 V; ~36 % of the 6 A
  `+5V_SOM` buck. Estimate, to be refined at bring-up.

- **Connector-only sheet.** The netlist adds no discretes; the placement engine's
  connector-fan template fires only for a lone ≥40-pin part, so carrier-side straps
  (e.g. the PUDC pull) live on other sheets and the diff-pair/SD-bus typing is the
  only on-sheet annotation.

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J1 | DF40C-100DP-0.4V(51) | `parts/DF40C-100DP-0.4V_51/` (100 signal + 4 hold-down pads) | C531031 |

## Build & test

`test_som_j1.py` is an offline correctness test (model completeness, design-rule
slice, sheet invariants). Run it with:

```
pytest devkit_mini/subsystems/som_j1/test_som_j1.py
```
