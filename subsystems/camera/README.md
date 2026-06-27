# camera — Raspberry-Pi 15-pin FFC, 2-lane MIPI CSI-2 port (reusable subsystem)

A project-agnostic, self-contained schgen subsystem: a Raspberry-Pi 15-pin FFC
camera port carrying **2 data + 1 clock** MIPI CSI-2 D-PHY lanes, with fixed
external host-side differential terminations, low-capacitance ESD clamps, a
camera-control I2C bus, and a gated module-power rail. It declares its interface
as **abstract** port + rail names and knows nothing about any consuming board; a
project supplies a **bind map** (`abstract -> real net`) to drop it onto real
nets. It is the camera input for the Zynq-7000 SoM carrier.

## Interface

A consuming project supplies one standard `META` dict (`schgen.core.subsystem.Meta`)
and forwards it to `camera.circuit(META)`. The four keys are universal across every
reusable subsystem; an unknown top-level key is a hard `CircuitError`.

| key | role |
|-----|------|
| `bind`    | `{abstract_net: board_net}` — rebinds every externally-visible net (`+VDD_CAM`, `GND`, and the 10 ports) to the project's real names. Applied last, order-preserving, so binding to a hand-written sheet's names yields a byte-identical sheet. POWER/GROUND/PORT only; a SIGNAL key or a collision is a hard error. |
| `expects` | `{abstract_port: deferral}` — attaches an explicit linker deferral declaring which project sheet binds a deferred port (CSI lanes / control lines). |
| `buses`   | `{"i2c": name}` — the camera-control I2C bus-group name for `CAM_SCL`/`CAM_SDA` (defaults to abstract `CAM_CCI`, 400 kHz). |
| `notes`   | `{"draws": prose}` — the power-tree draw-note prose (defaults to the RPi V2/IMX219 budget). |

With `meta=None` the subsystem keeps its abstract names so `test_camera.py` runs offline.

### Rails

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VDD_CAM` | POWER  | gated camera module rail (3.3 V class), FFC pin 15. A project **must** supply a gated rail here: the I2C pull-ups land on it, so a powered-down camera is not back-fed through its own bus pull-ups. Local 100n + 10u bypass at the connector live in this subsystem. Budget ~300 mA. |
| `GND`      | GROUND | ground — FFC grounds (1/4/7/10), the two mounting-plate tabs (16/17), and the ESD-array GND pads. |

### Ports

| abstract | type | FFC pin(s) | meaning |
|----------|------|-----------|---------|
| `CSI_D0_P` / `CSI_D0_N` | diff_pair @100R | 3 / 2 | CSI-2 data lane 0 (N before P on the FFC). |
| `CSI_D1_P` / `CSI_D1_N` | diff_pair @100R | 6 / 5 | CSI-2 data lane 1. |
| `CSI_CLK_P` / `CSI_CLK_N` | diff_pair @100R | 9 / 8 | CSI-2 clock lane. |
| `CAM_SCL` / `CAM_SDA` | i2c (bus `CAM_CCI`, 400 kHz) | 13 / 14 | camera-control I2C (MIPI CCI class); 4k7 pull-ups to `+VDD_CAM` live here. |
| `CAM_EN`  | single | 11 | module power-enable / shutdown (RPi `CAM_GPIO0`). |
| `CAM_LED` | single | 12 | LED indicator (RPi `CAM_GPIO1`, v1-module only — kept routed). |

D-PHY pairs are **not** polarity-swappable (P→P, N→N). The diff-pair typing is
authored reciprocally so a router/linker sees the pairing both ways; binding
preserves it, keeping the derived `layout_constraints.csv` pair_with / length-match
group and the XDC pair byte-stable.

## Design

- **Reference connector — Amphenol SFW15R-1STE1LF (LCSC C3168538).** 1.0 mm pitch,
  15-position, **bottom-contact** FFC (contact orientation verified against Amphenol
  drawing 10172241). FFC pad *n* = RPi camera FFC pin *n*; the bare-number FFC pins
  stay numeric. The connector symbol/footprint and MPN come from the global parts
  library entry, and the board-level netlist gate proves KiCad sees every FFC pad.

- **HS-RX termination (Xilinx XAPP894).** The host uses the Xilinx XAPP894
  "7-series + external passives" topology to receive MIPI D-PHY: a **fixed external
  100R** differential termination per pair (R1–R3), placed at the FPGA/SoM-connector
  **end** of each trace — not at the FFC. R1–R3 stay **populated**: a 7-series HR-bank
  RX cannot gate `DIFF_TERM`, so the fixed 100R is required for HS reception and is
  not redundant. Low-Power (LP) observability — driving/sensing the lanes single-ended
  below the HS burst — is handled by the XAPP894 LP resistor-divider DNP stuffing
  option, which lives off this FFC sheet (CAM-1).

- **ESD — two TI TPD4E02B04DQAR low-cap arrays (LCSC C106794).** 0.2 pF/line typ
  (well under the D-PHY budget), 8 kV contact / IEC 61000-4-2. U1 clamps the 4 CSI
  data lines (D0 + D1, channels IO1–IO4); U2 clamps the CLK pair (IO1/IO2). The two
  spare U2 channels (IO3 = pad 4, IO4 = pad 5) clamp the cable-facing I2C control
  lines `CAM_SCL`/`CAM_SDA` — the same FFC, so the slow lines get GND-referenced ESD
  for free (0.2 pF negligible at 400 kHz). All clamps are DC-coupled **shunt taps**
  added to the existing line nets (never in series), so the netlist proves
  `{J1.pin, term, U.IOn}` per line. The arrays are GND-referenced (no VCC), so they
  remain valid and cannot be back-powered when the gated `+VDD_CAM` is off. The
  remaining USON-10 spare pads stay NC (U1: 6/7/9/10; U2: 6/7/9/10). `CAM_EN`/`CAM_LED`
  stay unclamped — no spare channels remain, an accepted trade for static GPIO.

- **Gated rail + pull-ups (back-feed).** The 4k7 I2C pull-ups (R4, R5) tie to the
  gated `+VDD_CAM`, so a powered-down camera is not back-fed through its own bus
  pull-ups. `CAM_EN` gives a logic-level shutdown independent of the rail gate. At
  the connector: 100n (C1) + 10u (C2) local bypass.

- **Bring-up.** Testpoints on `CAM_SCL`, `CAM_SDA`, and `CAM_EN` make the control
  bus and the module enable probeable. Power-tree budget: 300 mA on `+VDD_CAM`
  (RPi V2/IMX219 typ ~250 mA incl. the I2C pull-ups).

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J1 | SFW15R-1STE1LF | `parts/SFW15R-1STE1LF/` (1.0 mm 15P bottom-contact FFC) | C3168538 |
| R1–R3 | 100R | `Device:R` (D-PHY diff terminations) | C22775 |
| R4, R5 | 4k7 | `Device:R` (`CAM_SCL`/`CAM_SDA` pull-ups to `+VDD_CAM`) | C23162 |
| C1 | 100n | `Device:C` (`+VDD_CAM` bypass) | C14663 |
| C2 | 10u  | `Device:C` (`+VDD_CAM` bulk)   | C15850 |
| U1, U2 | TPD4E02B04DQAR | `parts/TPD4E02B04DQAR/` (low-cap 4-ch ESD array, 0.2 pF/line) | C106794 |

## Build & test

`test_camera.py` runs the subsystem-local slices offline: declared abstract
interface, reciprocal diff-pair typing, model completeness (every FFC pad netted),
the I2C-pull-up design rule, part-rating + per-rail cap-derating coverage, the SPICE
subckt ↔ netlist passive match, and the bind/meta contract. Cross-board gates (link
graph, full power-tree headroom, board ERC, netlist merge) run at board level via
`schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/camera/test_camera.py -q
```
