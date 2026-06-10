# HDMI-019S - HDMI Type-A receptacle, 19-pin SMD

SOFNG HDMI-019S (LCSC C111617) is the HDMI 1.4 Type-A receptacle used
twice on the carrier (one HDMI TX port, one HDMI RX port). Mechanical-
only datasheet in this folder; signal definitions follow HDMI 1.4b
Section 4.2.

## Rails

| Rail           | Pin  | Direction | Notes                                           |
|----------------|------|-----------|-------------------------------------------------|
| `+5V`          | 18   | TX: output, RX: input | +5V VBUS to/from upstream/sink     |
| `GND` (signal) | 17 + shields 2/5/8/11 | passive | DDC/CEC and TMDS shields    |
| `CHASSIS_GND`  | shell legs | passive | Frame ground (AC-coupled to signal GND) |

## Key external parts

Per HDMI 1.4 Section 4.2.7 (VBUS and shield handling):

| From pin | To net         | Part token         | Qty | Why                                              |
|----------|----------------|--------------------|-----|--------------------------------------------------|
| +5V      | GND            | `1u_0402_X7R`      | 1   | VBUS bulk to absorb load-switch turn-on transient|
| +5V      | GND            | `100n_0402_X7R`    | 1   | VBUS HF bypass at the connector pin              |
| SHIELD   | CHASSIS_GND    | `1M_0402_1%`       | 1   | DC bleed: drain static charge to chassis         |
| SHIELD   | CHASSIS_GND    | `100n_0402_X7R`    | 1   | HF return path for EMC compliance                |

NO external pull-ups on DDC SCL/SDA, CEC, or HPD: the TPD12S016
companion sitting between Zynq and this connector provides all of
them internally (TPD12S016 DS Sec 7.3.9, 7.3.15).

## Layout constraints

* TMDS pairs (D2, D1, D0, CLK): 100 ohm differential impedance,
  length-matched within 0.5mm intra-pair.
* Inter-pair skew across the four TMDS pairs: <= 2mm length difference.
* Place the TPD12S016 companion within 10mm of pin 1; route TMDS
  straight through the protection device before any vias.
* Connector shell legs route to a CHASSIS_GND copper island only.
  That island bonds to signal GND at a single star point near the
  carrier's power-entry connector.
* Keep DDC SDA/SCL traces <= 50mm long and clear of TMDS pairs.

## Carrier usage

* `blocks/hdmi_tx.py` - source role, connects to `TPD12S016PWR_TX`,
  pin 18 sources +5V VBUS, pin 19 is HPD input from sink, DDC bus
  carries EDID transactions with the carrier's on-board 24LC256 EDID
  EEPROM (see `components/eeprom_24lc256_edid`).
* `blocks/hdmi_rx.py` - sink role, connects to `TPD12S016PWR_RX`,
  pin 18 senses upstream +5V, pin 19 is HPD output to source.
