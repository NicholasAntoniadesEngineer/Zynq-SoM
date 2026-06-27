# som_j3 — SoM mezzanine connector J3 (FPGA bank 33/34/35 IO + VCCO rails)

`som_j3` is the carrier-side **J3** DF40 mezzanine connector that mates the SoM.
It carries the FPGA bank 33/34/35 half of the SoM↔carrier contract: the LCD
RGB888 + sync bus (bank 34), the camera CSI lanes and control (bank 33/35), the
FMC clocks and LA pairs (bank 35), the board-supervisor watchdog (bank 33), the
PUDC config strap (bank 34), and the bank-34/35 VCCO supply rails. It is a
connector-only sheet: just the receptacle and its net binds, no discretes.

## Interface

This is a **carrier-local** subsystem — it is the SoM side of the contract by
construction, so every port resolves against `carrier/som_interface.json` and is
consumed by name from the carrier feature sheets (`lcd`, `camera`, `fmc`,
`board_services`, `bringup_rails`).

`som_j3.py` calls the shared generator `carrier/som_conn_gen.py`:

```python
def circuit():
    return _gen.connector_circuit(
        "J3", "som_j3", "SoM J3: FPGA bank 33/34/35 IO + VCCO rails")
```

The generator loads J3's pin→net map from `som_interface.json` and binds every
signal pin (1–100) to its contract net, applying the carrier function map, the
PUDC strap port, the VCCO rail tie, and the camera/FMC differential-pair typing.
The 4 hold-down pads (101–104) of the DP plug are mechanical and emitted as
explicit no-connects.

Nets J3 drives:

| net | class | role |
|-----|-------|------|
| `+3V3` | POWER | VCCO source for Zynq bank 34 (LCD LVCMOS33); the `+VCCO_34` contacts (J3.97/99) merge onto the carrier `+3V3` rail as in-fan rail taps. Declared draw 0.010 A. |
| `+2V5_VADJ` | POWER | VCCO source for Zynq bank 35 (LVDS_25 camera/FMC); the `+VCCO_35` contacts (J3.1/2/4) merge onto the carrier `+2V5_VADJ` rail. Declared draw 0.050 A. |
| `GND` | GROUND | ground return (21 contacts). |
| signal ports | PORT | the bank 33/34/35 function nets below. |

Signal ports (consumer sheet binds the same name):

- **LCD RGB888** (bank 34) — `LCD_R0..7`, `LCD_G0..7`, `LCD_B0..7`, `LCD_PCLK`,
  `LCD_HSYNC`, `LCD_VSYNC`, `LCD_DE`, `LCD_DISP`, `LCD_BL_PWM`.
- **Camera** (bank 33/35) — `CAM_CLK_{P,N}` (J3.9/11), `CAM_D0_{P,N}` (J3.5/7),
  `CAM_D1_{P,N}` (J3.17/15), typed `diff_pair` 100Ω MIPI CSI, plus control
  `CAM_SCL`, `CAM_SDA`, `CAM_EN`, `CAM_LED` (J3.86/89/85/87).
- **FMC** (bank 35) — `FMC_CLK0_M2C_{P,N}`, `FMC_CLK1_M2C_{P,N}`,
  `FMC_LA00_CC_{P,N}`, `FMC_LA01_CC_{P,N}`, `FMC_LA02..07_{P,N}` (typed
  `diff_pair` 100Ω).
- **Watchdog** (bank 33, +3V3 domain) — `WATCHDOG_RST_N` (TPS3823-33 RESET# → PL,
  J3.98) and `WATCHDOG_KICK` (PL → WDI, J3.96).
- **PUDC** (bank 34) — `PUDC_34` (J3.39): the pull-up-during-config pin, exposed
  as a function port; its 10k-to-GND strap resistor lives on `bringup_rails`.
- **ESC PWM** (bank 33) — `ESC_PWM_IN4..7` (J3.91/93/92/94): spare bank-33 PL
  pins routed to the motor-PWM buffer.
- **Spares** — verbatim `IO_L*_33/34/35` ports for unmapped bank pins, kept for
  probe/expansion.

## Design

- **Connector part** — `DF40C-100DP-0.4V(51)`, the Hirose 0.4 mm-pitch 100-pin
  **plug** (DP). The carrier carries the plug because DF40 mates only
  plug-to-receptacle; the SoM is fabricated with the DS receptacle, so two
  receptacles would not interlock. Signal pins keep the same net→pad-number map
  (the DP/DS pair mates pad-N to pad-N), and the DP's 4 extra hold-down pads
  (101–104) are mechanical and no-connected.

- **VCCO rails are real sourced loads.** The carrier must source every Zynq bank
  VCCO or all bank I/O is dead. Bank 34 (LVCMOS33) takes `+3V3`; bank 35
  (LVDS_25, shared camera/FMC 2.5 V) takes `+2V5_VADJ`. Each `+VCCO_*` contact
  pin merges onto its carrier rail as one more tap; the rail's own buck/LDO is
  the source, so these appear as power draws (0.010 A and 0.050 A), not orphan
  nets.

- **Watchdog on the +3V3 domain.** `WATCHDOG_RST_N` and `WATCHDOG_KICK` are
  placed on bank-33 (+3V3, LVCMOS33) PL pins so both share the TPS3823-33
  monitor's 3.3 V domain. The TPS3823-33 has VIT- = 2.93 V and must stay on a
  3.3 V rail; on a 2.5 V rail it would assert RESET permanently. LVCMOS33 drive
  also clears the WDI input threshold (VIH = 0.7·VDD = 2.31 V) that a 2.5 V
  LVCMOS output could not.

- **Differential-pair typing.** The camera CSI and FMC LVDS pairs are typed
  `diff_pair` at 100Ω on this sheet so the constraints exporter sees both ends
  of each pair where they enter the connector.

- **Connector-only sheet.** No discretes — only the receptacle and its net
  binds. The PUDC strap resistor that this pin needs lives on `bringup_rails`,
  keeping the connector sheet pure so the placement engine's connector-fan
  template applies.

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J3 | DF40C-100DP-0.4V(51) | `parts/DF40C-100DP-0.4V_51/` (100 signal + 4 hold-down pads) | C531031 |

## Build & test

`test_som_j3.py` runs the subsystem-local slices offline (model completeness,
design-rule/part/spice slices, and sheet invariants: VCCO rails, camera/FMC
diff-pair typing, key function ports, the `.cir` subckt stub).

```
pytest carrier/subsystems/som_j3/test_som_j3.py
```
