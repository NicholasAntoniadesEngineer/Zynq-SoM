# power_mon — 2x INA3221 rail telemetry (+VIN, +5V, +3V3, +1V8)

Rail current/voltage monitoring for the four carrier supply rails, on the
always-on management I2C bus. Two TI **INA3221** triple monitors at **0x40**
(A0=GND) and **0x41** (A0=VS) on the shared `STM32_I2C2` bus, with series sense
shunts (`RS1..RS4`) inserted in each rail.

This is a **carrier-LOCAL** subsystem: it is folded into the `<name>/<name>.py`
package layout (same 4-artifact parity as the generic `subsystems/<name>/`
library) but wires the carrier's REAL net names directly — no abstract interface
/ `META` bind contract.

## Package contents

| file | role |
|------|------|
| `power_mon.py`      | the NETLIST — `circuit()` returning the carrier `Circuit` |
| `power_mon.cir`     | SPICE subckt — the sense-shunt resistor network (RS1..RS4) + the supply decoupling, with the carrier externals as subckt pins |
| `test_power_mon.py` | LOCAL electrical-correctness test (offline: model completeness + decap/EP slice + ratings + shunt invariants + the address-strap/alert map + SPICE-passive match) |
| `README.md`         | this file |

## Parts (live-verified on JLCPCB)

| ref | part | LCSC | role |
|-----|------|------|------|
| U1  | `INA3221AIRGVR` | C181255 | triple I2C current/bus-voltage monitor — **0x40** (A0=GND): ch1 +VIN, ch2 +5V, ch3 +3V3 |
| U2  | `INA3221AIRGVR` | C181255 | triple I2C current/bus-voltage monitor — **0x41** (A0=VS): ch1 +1V8 (ch2/ch3 unused, inputs to GND) |
| RS1 | `RLM12FTCMR010` 10mR | C188070 | +VIN sense shunt (30 mV @ 3 A, 4 mA LSB) — `+VIN -> +VIN_SYS` |
| RS2 | `RLM12FTCMR010` 10mR | C188070 | +5V sense shunt — `+5V_REG -> +5V` |
| RS3 | `RLM12FTCMR010` 10mR | C188070 | +3V3 sense shunt — `+3V3_REG -> +3V3` |
| RS4 | `RLM12FTCMR020` 20mR | C393094 | +1V8 sense shunt (12 mV @ 600 mA, 2 mA LSB) — `+1V8_REG -> +1V8` |
| C1 / C2 | 100n | C14663 | per-IC supply bypass (`+3V3_SC -> GND`) |
| C3  | 10u | C15850 | bulk supply decoupling (`+3V3_SC -> GND`) |
| R1  | 10k | C25804 | `PMON_ALERT_N` pull-up to `+3V3_SC` (defined-high) |

## Shunts (the DEF-D rail split)

Each rail nets SPLIT at its shunt so each channel reads only its own rail's loads.
`power` / `power_som` put each regulator's OUTPUT cluster on the `_REG` net and the
buck INPUTs on `+VIN_SYS`; the board-facing rail lives on the load side, with the
shunt in series between them:

| shunt | reg/source side (IN+) | board/load side (IN-) | value |
|-------|-----------------------|-----------------------|-------|
| RS1 | `+VIN` (PD entry, usb_pd sense) | `+VIN_SYS` (buck inputs) | 10 mR |
| RS2 | `+5V_REG` (buck-1 output cluster) | `+5V` (board rail) | 10 mR |
| RS3 | `+3V3_REG` (buck-2 output cluster) | `+3V3` (board rail) | 10 mR |
| RS4 | `+1V8_REG` (LDO output cluster) | `+1V8` (board rail) | 20 mR |

## Supply, address map, alert

- **Always-on supply.** Both ICs run from `+3V3_SC` (the always-on SoM SC rail) so
  telemetry works with every monitored rail down. `VS` + `VPU` tie to `+3V3_SC`;
  `GND` + the exposed `PAD` tie to GND.
- **Address straps.** `U1.A0 -> GND` (0x40), `U2.A0 -> +3V3_SC` (0x41). The whole
  carrier address map: 0x20 TCA9535 / 0x22 FUSB302B / **0x40-0x41 INA3221** / 0x50
  FMC-EEPROM / 0x51 ID-EEPROM / 0x52 RTC — no collisions.
- **Alert.** Both CRITICAL pins (open-drain) wire-OR into `PMON_ALERT_N` (10k
  pull-up to `+3V3_SC`) for the bringup expander's spare port P11. WARNING / PV /
  TC stay I2C-readable and are author no-connects.
- **No I2C pull-ups here.** `usb_pd` / `bringup` own the `STM32_I2C2` bus pulls.

## Notes

- **Unused U2 channels.** `U2` ch2/ch3 inputs (`IN+2/IN-2/IN+3/IN-3`) tie to GND
  per the datasheet (reads 0 V / 0 A) — only ch1 (+1V8) is wired.
- **AMX-2 common-mode headroom.** The +VIN channel sense pins (IN+1 on `+VIN`,
  IN-1 on `+VIN_SYS`) keep ~3 V margin to the INA3221 26 V common-mode abs-max at
  the eFuse OVP-trip corner (+VIN can reach ~23.06 V before cutoff) — positive in
  every corner. That headroom is COUPLED to the pd_input eFuse OVP setpoint (PD-1):
  any future widening of the OVP trip must re-check this 26 V limit.

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/power_mon/test_power_mon.py -q
```

The board-level gates (the cross-sheet I2C pull-up completeness, the link/port
graph, board ERC and the netlist merge) stay aggregated by `schgen board`.
