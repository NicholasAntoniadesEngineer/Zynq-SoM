# board_services — ID-EEPROM (MAC) + RTC + watchdog on the gated +3V3_AUX rail

The four board-management services the Zynq carrier was missing, all powered
from the **manually-gated `+3V3_AUX` rail** (the gate + I2C isolator that feed
them live on `board_aux`; the QWIIC connector that re-exports the bus lives on
`board_qwiic`). This is a **carrier-LOCAL** subsystem: it is folded into the
`<name>/<name>.py` package layout (so it gets the same 4-artifact parity as the
generic `subsystems/<name>/` library) but it wires the carrier's REAL net names
directly — it is not a project-agnostic, bind-mapped library subsystem, so there
is no abstract interface / `META` contract here.

## Package contents

| file | role |
|------|------|
| `board_services.py`      | the NETLIST — `circuit()` returning the carrier `Circuit` |
| `board_services.cir`     | SPICE subckt — the passive network (decoupling + INT# pull-up + the RTC coin-cell node) with the external nets as subckt pins |
| `test_board_services.py` | LOCAL electrical-correctness test (offline: model completeness + decap/strap slice + ratings + SPICE-passive match + the address/part invariants) |
| `README.md`              | this file |

## Parts

| ref | part | MPN / lib | LCSC | role |
|-----|------|-----------|------|------|
| U1  | ID-EEPROM   | `24AA025E48T-I_OT` | C (parts lib) | 2 Kb I2C EEPROM with a factory-locked **EUI-48 MAC**, strapped to **0x51** |
| U2  | RTC         | `RV-3028-C7-32.768kHz-1ppm-TA-QC` | C (parts lib) | ultra-low-power I2C RTC, integrated 32.768 kHz DTCXO, coin-cell backed, **0x52** |
| U3  | supervisor  | `TPS3823-33DBVR` | C (parts lib) | supervisor + windowed watchdog (3.3 V threshold variant, VIT- = 2.93 V) |
| BT1 | cell holder | `KH-CR1220-2` | C (parts lib) | 12.5 mm coin-cell holder for the RTC backup cell (fit a **rechargeable ML1220**) |
| C1–C3 | 100n | `Device:C` | C14663 | one local supply bypass per IC (U1.VCC / U2.VDD / U3.VDD) |
| R1  | 1k   | `Device:R` | C21190 | WDI series resistor (ESD back-feed limiter on `WDI_AUX`) |
| R2  | 10k  | `Device:R` | C25804 | RTC INT# pull-up to `+3V3_AUX` |

## The I2C bus and address map

The EEPROM and RTC live on **`AUX_I2C`** — the PCA9306-isolated segment of the
always-on `STM32_I2C2` management bus (the isolator is on `board_aux`). When
`+3V3_AUX` is OFF these chips are powered down AND cut off from the management
bus (no back-powering through their ESD diodes — LAW 0).

Full 7-bit address map (the whole carrier):

| addr | device | sheet | bus segment |
|------|--------|-------|-------------|
| 0x20 | TCA9535       | bringup_rails | STM32_I2C2 trunk (always-on) |
| 0x22 | FUSB302B      | usb_pd        | STM32_I2C2 trunk (always-on) |
| 0x40–0x41 | INA3221  | power_mon     | STM32_I2C2 trunk (always-on) |
| 0x50 | FMC-EEPROM    | fmc           | STM32_I2C2 trunk (always-on) |
| **0x51** | **ID-EEPROM (A0=1, A1=0)** | **board_services** | **AUX_I2C (gated)** |
| **0x52** | **RV-3028 RTC** | **board_services** | **AUX_I2C (gated)** |

No collisions. The two ports `AUX_I2C_SCL` / `AUX_I2C_SDA` (typed i2c, scl/sda,
bus `AUX_I2C`, 400 kHz) bind on `board_aux` (the isolator's side-2). The bus
pull-ups are SHARED and live ONCE on the AUX segment (`board_aux`'s 4k7 pulls),
never here.

## Notes (datasheet + bring-up contract)

- **Watchdog safety (C2: no reset during power-up).** Three independent guards,
  any one alone prevents a power-up reset:
  1. `U3.VDD` is `+3V3_AUX`, which **defaults OFF** (board_aux SW1) — the
     supervisor is physically unpowered through power-up.
  2. The TPS3823 **disables its watchdog** when WDI floats; WDI is driven only
     by the PL (`WATCHDOG_KICK`), Hi-Z until the fabric is configured.
  3. `RESET#` gates no rail/POR line — it rides a PL bank-33 IO
     (`WATCHDOG_RST_N`) as a firmware-mediated EVENT; a bite cannot hard-reset
     the board.
- **Watchdog voltage domain (audit fix 2026-06-16).** U3 monitors a 3.3 V rail
  (TPS3823-**33**, VIT- = 2.93 V) so it MUST stay on `+3V3_AUX`. BOTH watchdog
  nets were relocated off bank 35 (+2V5_VADJ / LVCMOS25) onto SPARE bank-33
  +3V3 (LVCMOS33) PL pins so U3's 3.3 V push-pull I/O no longer crosses into a
  2.5 V VCCO bank: `RESET#` no longer forward-biases the Zynq input clamp diode
  (chronic Iin stressor), and `WDI`'s LVCMOS33 drive (VOH ~3.0 V) now clears the
  TPS3823 WDI threshold VIH = 0.7·VDD = 2.31 V (the old LVCMOS25 ~2.1 V could
  not). `WATCHDOG_KICK` → IO_L4_N_33 (J3.96); `WATCHDOG_RST_N` → IO_L4_P_33
  (J3.98). The reset-RC rule is **waived** here (RESET# is a push-pull event
  output, not a POR line — no pull, no cap by design).
- **RTC backup cell.** BT1 is a **rechargeable ML1220** (Mn-Li); the SC firmware
  enables the RV-3028 trickle charger so the cell tops up whenever the board is
  powered. Do NOT fit a primary CR1220 (it would be charged) or a LIR Li-ion
  (its 4.2 V charge target exceeds the 3.3 V supply). The KH-CR1220-2 holder
  fits both 12.5 mm chemistries. The VBACKUP decap rule is **waived** on the
  `V_RTC_BAT` net (the RV-3028 regulates internally; a cap on the cell is
  optional — no bypass fitted) — keyed on the net, NOT the ref, so `U2.VDD`
  stays under the decap rule.
- **Zynq-agnostic (C3).** The only SoM-side signals are the two watchdog lines,
  homed to spare PL bank-33 (+3V3) IO via the som_conn_gen FUNCTION_MAP; nothing
  here hard-codes the Zynq part.

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/board_services/test_board_services.py -q
```

The board-level gates (full power tree, board ERC, the cross-sheet I2C pull-up
and link/port-driver graph) stay aggregated by `schgen board`.
