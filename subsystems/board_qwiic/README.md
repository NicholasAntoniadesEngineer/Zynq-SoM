# board_qwiic — QWIIC / STEMMA-QT expansion connector + its ESD array

This carrier-local subsystem exposes the gated `+3V3_AUX` rail and the isolated
`AUX_I2C` bus on a standard 4-pin JST-SH (QWIIC) connector, so daughter
sensor/IO modules hang off the Zynq-7000 SoM carrier. Following the carrier's
connectors-get-their-own-sheet idiom (`rj45_connector`, `usb_uart_connector`),
the connector and its protection live here; the EEPROM/RTC/watchdog that share
the bus sit on `board_services`, and the rail gate + bus isolator sit on
`board_aux`.

## Interface

Carrier-local: it wires real carrier net names directly and exposes no abstract
`META` bind contract. It drives:

- `J1.2` ← `+3V3_AUX` (gated connector power) and `J1.1`/`J1.5`/`J1.6` ← `GND`
  (signal return plus shell/mounting tabs).
- Connector I2C: `QWIIC_SDA` (`J1.3`) and `QWIIC_SCL` (`J1.4`) enter the ESD
  array and exit as the typed ports `AUX_I2C_SDA` (`U1.6`) and `AUX_I2C_SCL`
  (`U1.4`) — i2c, 400 kHz, bus `AUX_I2C` — which link back to the isolated AUX
  I2C bus on `board_aux` / `board_services`.
- `U1.5` ← `+3V3` (always-on ESD clamp reference) and `U1.2` ← `GND`.
- A power-tree budget of 200 mA on `+3V3_AUX` for the external module.

## Design

- **Connector — JST-SH 4-pin (QWIIC/STEMMA-QT), `ZX-SH1.0-4PWT`.** Standard
  4-pin 1.0 mm pitch QWIIC receptacle carrying the convention GND / +3V3 /
  SDA / SCL (looking into the receptacle). Pads 5/6 are the shell/mounting tabs
  and tie to `GND`. Connector pad order must be verified at layout: confirm
  pad 1's location against the J1 footprint silk before fab, since a swapped
  power pad would damage external modules.
- **ESD — `USBLC6-2SC6` low-capacitance TVS array.** QWIIC is hot-plugged by
  hand, so SDA/SCL are clamped at the connector. The USBLC6 is the carrier's
  standard low-capacitance ESD array (~3.5 pF/line), low enough not to disturb
  400 kHz I2C. It uses the `1↔6` / `3↔4` passthrough idiom shared with
  `usbc_otg` / `usb_uart`: the external lines sit on `U1.1`/`U1.3`, and the
  protected pair reaching the isolated bus sits on `U1.6`/`U1.4`, with `GND` on
  `U1.2`.
- **Clamp reference is always-on, connector power is gated.** `U1.5` references
  the always-on `+3V3`, not the gated `+3V3_AUX`. The USBLC6 is passive — its
  I/O diodes are reverse-biased in normal operation, so the reference draws
  ~0 and never back-feeds the gated rail — and an always-on reference keeps the
  clamp valid in every power state, including the most ESD-exposed one: a module
  hot-plugged while the connector rail is OFF. The connector power (`J1.2`)
  stays gated `+3V3_AUX`.
- **Defense in depth.** Because the bus is also behind the `board_aux` PCA9306
  isolator, a strike here is both clamped at the connector and cut off from the
  always-on management bus.

## Parts

| ref | value | lib/part | LCSC |
|-----|-------|----------|------|
| J1  | QWIIC receptacle (4-pin JST-SH) | `ZX-SH1.0-4PWT` | parts lib |
| U1  | low-capacitance ESD array | `USBLC6-2SC6` | parts lib |

## Build & test

`test_board_qwiic.py` asserts model completeness plus the ESD passthrough and
always-on-clamp-ref / gated-connector-power invariants:

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/board_qwiic/test_board_qwiic.py -q
```
