# som_j2 — SoM mezzanine connector J2 (FPGA bank 13/33 IO + VCCO)

`som_j2` is the carrier-side half of the **J2** Hirose DF40 mezzanine link. It
carries the Zynq-7000 bank 13 and bank 33 I/O plus those banks' VCCO supply:
HDMI RX, HDMI TX, LCD capacitive-touch I2C, Pmod expansion, a fabric debug
UART, the PS UART0 modem lines, ESC PWM outputs, PL buttons, and SD card-detect.
It is a carrier-LOCAL, connector-only subsystem — no discretes, just the
receptacle's mating plug and its net binds.

## Interface

`som_j2.py` is a thin wrapper: it calls
`connector_circuit("J2", "som_j2", "SoM J2: FPGA bank 13/33 IO + VCCO rails")`
in the shared generator `devkit_mini/som_conn_gen.py`. The pin→net map for J2's 100
signal pins comes from `devkit_mini/som_interface.json` (extracted from the SoM
KiCad project by `schgen som-interface`). The generator binds every J2 pin to
its carrier net and exposes those nets to the rest of the carrier; consumer
sheets (hdmi_tx, hdmi_rx, lcd, uart_bridge, usb_jtag, motor_pwm, …) bind to the
same net names from their own sheets. Because these sheets ARE the SoM side of
the contract, J2 has no deferred ports — every port resolves here by
construction.

Each SoM contract pin resolves to its carrier net through `resolve_net()`, in
priority order:

1. **VCCO bank-rail tie** — a `+VCCO_*` pin merges onto the carrier rail that
   sources it (here `+VCCO_13` and `+VCCO_33` → `+3V3`).
2. **Function map** — an abstract PL pin name (`IO_L*_13/33`) is renamed to its
   concrete carrier function net (e.g. `IO_L16_P_13` → `LCD_CTP_SDA`).
3. **Verbatim** — anything unmapped (spares, `GND`) keeps its contract spelling.

### Rails

| net | class | role on J2 |
|-----|-------|------------|
| `+3V3` | POWER | VCCO source for banks 13 and 33 (LVCMOS33). The `+VCCO_13` (J2.1-3) and `+VCCO_33` (J2.98-100) contact pins merge onto the carrier `+3V3` rail as taps; the carrier buck is the source. |
| `GND` | GROUND | ground return. |

### Signal ports (consumer binds the same name)

- **HDMI RX** (bank 33) — `HDMI_RX_CLK_{P,N}`, `HDMI_RX_D{0,1,2}_{P,N}` (typed `tmds_pair`), `HDMI_RX_CEC`, `HDMI_RX_5V_DET`.
- **HDMI TX** (bank 33) — `ZYNQ_HDMI_TX_TMDS_{CLK,0,1,2}_{P,N}` (typed `tmds_pair`), `ZYNQ_HDMI_TX_{SCL,SDA,CEC,HPD}`.
- **LCD touch** (bank 13) — `LCD_CTP_{SDA,SCL,RST,INT}`.
- **Pmod expansion** (bank 13) — `PMODX_IO1..8`, eight free LVCMOS33 PL pins.
- **PS UART0 modem** (bank 13, EMIO) — `ZYNQ_PS_UART0_{CTS_N,RTS_N}`.
- **Debug UART** (bank 13) — `DBG_UART_{RXD,TXD}` (FT2232H channel-B fabric UART).
- **ESC PWM** (bank 13/33) — `ESC_PWM_IN0..3`, `ESC_BUF_OE_N`, `ESC_FAULT_N`.
- **PL misc** — `PL_BTN0`, `PL_BTN1`, `SD_CARD_DETECT` (PS SDIO0 CD via EMIO).
- **Bank-13/33 spares** — verbatim `IO_L*` ports (e.g. `IO_L6_P_33` on J2.89) kept for probe/expansion.

## Design

- **Carrier carries the plug.** J2 instantiates the DF40 **DP plug**
  (`parts/DF40C-100DP-0.4V_51/`). The SoM is fabricated with the DF40 **DS
  receptacle**, and DF40 mates only DP-plug ↔ DS-receptacle, so the carrier
  must supply the plug for the link to mate. The plug's four hold-down pads
  (101–104) are mechanical nails and are emitted as explicit author
  no-connects.
- **VCCO is a real, sourced load.** Banks 13 and 33 are LVCMOS33, so their
  `+VCCO_*` pins must be driven from the carrier `+3V3` buck output. Left
  floating, the bank VCCO is unpowered and all PL I/O on those banks is dead;
  the tie is therefore bound, not deferred, and each contiguous tap cluster is
  fanned as its own short trunk and power symbol on the sheet.
- **Pmod and ESC drive are 3.3 V-safe by construction.** Because bank 13/33
  VCCO is `+3V3`, the LVCMOS33 output levels into the Pmod headers and the ESC
  buffer A-side are correct by construction — no level translation on J2.
- **HDMI pairs are typed.** The eight HDMI RX/TX pairs are typed `tmds_pair`
  on the sheet so the constraints exporter sees both ends matched to the
  consumer HDMI sheets.
- **Connector-only sheet.** With no discretes, the placement engine
  (`schgen/place.py`) derives the two-column label fan, per-rail trunks, and
  PWR_FLAG row from the topology of the lone ≥40-pin connector alone.

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J2 | DF40C-100DP-0.4V(51) | `parts/DF40C-100DP-0.4V_51/` (100 signal + 4 hold-down pads) | C531031 |

## Build & test

`test_som_j2.py` is an offline local test (model completeness, design-rule
slice, sheet invariants). Run it with:

```
pytest devkit_mini/subsystems/som_j2/test_som_j2.py
```
