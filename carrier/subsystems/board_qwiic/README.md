# board_qwiic — QWIIC / STEMMA-QT expansion connector + its ESD array

The Zynq carrier exposes its gated `+3V3_AUX` rail and the isolated `AUX_I2C`
bus on a standard 4-pin JST-SH (QWIIC) connector so daughter sensor/IO modules
hang off the board. Following the carrier's connectors-get-their-own-sheet idiom
(`rj45_connector`, `usb_uart_connector`), the connector and its protection live
here; the EEPROM/RTC/watchdog that share the bus are on `board_services` and the
gate + isolator on `board_aux`. This is a **carrier-LOCAL** subsystem (real
carrier net names wired directly — it is a pure connector + ESD sheet, no
abstract-interface `META` bind contract).

## Package contents

| file | role |
|------|------|
| `board_qwiic.py`      | the NETLIST — `circuit()` returning the carrier `Circuit` |
| `board_qwiic.cir`     | SPICE subckt — minimal (a pure connector + passive ESD array adds no R/C network; the array is a passive clamp), with the external nets as subckt pins |
| `test_board_qwiic.py` | LOCAL electrical-correctness test (offline: model completeness + decap/strap slice + the ESD passthrough / always-on-clamp-ref invariants) |
| `README.md`           | this file |

## Parts

| ref | part | MPN / lib | LCSC | role |
|-----|------|-----------|------|------|
| J1  | QWIIC receptacle | `ZX-SH1.0-4PWT` | C (parts lib) | 4-pin JST-SH (GND / +3V3 / SDA / SCL standard) |
| U1  | ESD array | `USBLC6-2SC6` | C (parts lib) | low-capacitance TVS array (~3.5 pF/line), clamps the two I2C lines |

## The bus

The connector's SDA/SCL go **through** the ESD array, not straight to the bus:

- external lines at the connector sit on `U1.1` (`QWIIC_SDA`) / `U1.3`
  (`QWIIC_SCL`);
- the protected pair that reaches the isolated bus is on `U1.6` (`AUX_I2C_SDA`)
  / `U1.4` (`AUX_I2C_SCL`) — the same 1↔6 / 3↔4 passthrough idiom as
  `usbc_otg` / `usb_uart`.

The two ports `AUX_I2C_SDA` / `AUX_I2C_SCL` (typed i2c, 400 kHz, bus `AUX_I2C`)
link back to `board_aux` / `board_services`. Because the bus is also behind the
board_aux PCA9306 isolator, a strike here is both CLAMPED and CUT OFF from the
always-on management bus.

## Notes (ESD + power)

- **ESD on every external connector.** QWIIC is hot-plugged by hand, so its
  I2C lines are clamped at the connector by the carrier's standard
  USBLC6-2SC6 low-capacitance array (fine for 400 kHz I2C).
- **Clamp reference is ALWAYS-ON (LAW 0).** `U1.5` references the **always-on
  `+3V3`**, NOT the gated `+3V3_AUX`. The USBLC6 is passive (its I/O diodes are
  reverse-biased in normal operation, drawing ~0 and never back-feeding the
  gated rail), and an always-on reference keeps the clamp valid in EVERY power
  state — including the most ESD-exposed one, a module hot-plugged while the
  connector rail is OFF. The connector POWER (`J1.2`) stays gated `+3V3_AUX`
  (constraint C1). The local test asserts both: clamp ref on `+3V3`, connector
  power on `+3V3_AUX`.
- **QWIIC pad order — VERIFY AT LAYOUT.** Pads 1..4 are wired to the QWIIC
  standard GND / +3V3 / SDA / SCL (looking into the receptacle); confirm pad 1's
  location against the J1 footprint silk before fab, since a swapped power pad
  would damage external modules. Pads 5/6 are the shell/mounting tabs → GND.
- External-module headroom (200 mA) on the gated rail is declared for the power
  tree.

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/board_qwiic/test_board_qwiic.py -q
```

Board-level gates (full power tree, board ERC, the cross-sheet link /
port-driver graph) stay aggregated by `schgen board`.
