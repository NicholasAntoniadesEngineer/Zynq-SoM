# som_j2 — SoM mezzanine connector J2 (carrier-local subsystem)

The carrier side of the **J2** Hirose **DF40C-100DP-0.4V(51)** mezzanine
receptacle. J2 carries the **FPGA bank 13/33 IO + VCCO rails** half of the SoM
contract (HDMI RX/TX, LCD touch, Pmod expansion, PS UART0 modem lines, PL
buttons, FMC-present, SD card-detect, and the bank-13/33 VCCO supply).

This is a **carrier-LOCAL** subsystem (the SoM side of the contract by
construction), foldered into a per-name package for 4-artifact parity with the
generic `subsystems/<name>/` library.

## How it is generated (never hand-typed)

`som_j2.py` loads the shared generator `carrier/som_conn_gen.py` and calls
`connector_circuit("J2", "som_j2", "SoM J2: FPGA bank 13/33 IO + VCCO rails")`.
The pin→net map comes from `carrier/som_interface.json`; the generator binds
every J2 pin verbatim, applies the wave-3 FUNCTION map (renaming abstract
`IO_L*_13/33` PL pins to their carrier functions), ties each `+VCCO_*` contact
onto its carrier rail, and types the HDMI TMDS pairs. No hand-typed pinout.

## Package contents

| file | role |
|------|------|
| `som_j2.py`       | the NETLIST — `circuit()` instantiating the DF40 receptacle bound to the J2 contract |
| `__init__.py`     | re-exports `circuit` |
| `som_j2.cir`      | SPICE subckt stub — externally-visible nets as pins; a pure connector carries no on-sheet passive network |
| `test_som_j2.py`  | LOCAL correctness test (offline: model completeness + design-rule slice + sheet invariants) |
| `README.md`       | this file |

## The connector — part

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J2 | DF40C-100DP-0.4V(51) | `parts/DF40C-100DP-0.4V_51/` (100 bare-number pins) | C531031 |

## Interface it carries (the J2 contract)

### Rails (POWER / GROUND)

| net | class | source / note |
|-----|-------|---------------|
| `+3V3` | POWER  | VCCO source for Zynq banks **13 + 33** (LVCMOS33). The `+VCCO_13`/`+VCCO_33` contact pins MERGE onto the carrier +3V3 rail (SYS-1 in-fan rail tap); the carrier buck is the source. Declared draw 0.020 A (LVCMOS33 static + PL output drive + on-SoM BMI323 VDDIO rider). |
| `GND`  | GROUND | ground. |

### Signal ports (PORT, 72 total)

Highlights (consumer sheet binds the same name):

- **HDMI RX** (bank 33) — `HDMI_RX_CLK_{P,N}`, `HDMI_RX_D{0,1,2}_{P,N}` (typed `tmds_pair` 100R), `HDMI_RX_CEC`, `HDMI_RX_5V_DET`.
- **HDMI TX** (bank 33) — `ZYNQ_HDMI_TX_TMDS_{CLK,0,1,2}_{P,N}` (typed `tmds_pair` 100R), `ZYNQ_HDMI_TX_{SCL,SDA,CEC,HPD}`.
- **LCD touch** (bank 13) — `LCD_CTP_{SDA,SCL,RST,INT}`.
- **Pmod expansion** (bank 13) — `PMODX_IO1..8` (eight free LVCMOS33 PL pairs).
- **PS UART0 modem / debug** — `ZYNQ_PS_UART0_{CTS_N,RTS_N}` (EMIO), `DBG_UART_{RXD,TXD}` (FT2232H channel B fabric UART).
- **PL misc** — `PL_BTN0`, `PL_BTN1`, `SD_CARD_DETECT` (PS SDIO0 CD via EMIO). (`FMC_PRSNT_N` was retired when the FMC LPC site became a generic 2.54 mm header — `IO_L6_P_33`/J2.89 is now an unclaimed bank-33 spare.)
- **Bank-13 spares** — verbatim `IO_L*_13` / `IO_25_13` ports kept for probe/expansion.

## Notes

- **Connector-only sheet**: no discretes; only the receptacle and its net binds.
- VCCO is a real, sourced load (the carrier +3V3 buck), so it appears as a power
  draw, not a deferred orphan.
- Byte-identical: foldering this subsystem changed no emitted schematic or render.
