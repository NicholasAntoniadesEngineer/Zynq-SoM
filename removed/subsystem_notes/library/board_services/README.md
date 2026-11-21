# board_services — ID-EEPROM (MAC) + RTC + watchdog on the gated +3V3_AUX rail

Board-management peripherals for the Zynq-7000 SoM carrier: a factory-MAC
ID-EEPROM, a coin-cell-backed RTC, and a supervisor/watchdog. All three ride the
manually-gated `+3V3_AUX` rail and share the PCA9306-isolated `AUX_I2C` segment,
so they obey the same bring-up discipline as every other carrier module (manual
power enable). This is a carrier-LOCAL subsystem: it wires the carrier's real net
names directly and exposes no project-agnostic `META`/bind contract.

## Interface

`board_services` drives carrier nets directly; it binds to neighbouring sheets
through a small set of nets and typed ports:

- `+3V3_AUX` — the manually-gated 3.3 V supply (gate + PCA9306 isolator live on
  `board_aux`); powers all three ICs. When OFF, the ICs are unpowered AND cut off
  from the always-on management bus.
- `GND` — board ground.
- `AUX_I2C_SCL` / `AUX_I2C_SDA` — i2c ports (role scl/sda, bus `AUX_I2C`,
  400 kHz, `expect = board_aux`). `AUX_I2C` is the isolated side-2 of the
  always-on `STM32_I2C2` trunk; bus pull-ups live ONCE on `board_aux`, never here.
- `WATCHDOG_KICK` — port to PL bank-33 IO `IO_L4_N_33` (J3.96); PL → `U3.WDI`.
- `WATCHDOG_RST_N` — port to PL bank-33 IO `IO_L4_P_33` (J3.98); `U3.RESET#` → PL
  as a firmware-mediated event.
- `RTC_INT_N` — RV-3028 alarm output (local probe net).
- `V_RTC_BAT` — RTC coin-cell node (`U2.VBACKUP` ↔ `BT1.1`).

The watchdog FUNCTION names are emitted by the J-sheet generator's FUNCTION_MAP
(`som_conn_gen.py`); `xdc.py` constrains them live as bank-33 LVCMOS33. Nothing
here hard-codes the Zynq part.

## Design

**ID-EEPROM — `24AA025E48` @ 0x51.** A 2 Kb I2C EEPROM with a factory-locked,
globally-unique EUI-48 MAC, giving the LAN8720/RJ45 a hardware MAC instead of a
soft/random one. Address strapped to 0x51 via `A0 = +3V3_AUX` (1), `A1 = GND` (0).

**RTC — `RV-3028-C7` @ 0x52.** Ultra-low-power I2C RTC with an integrated
32.768 kHz DTCXO (no external crystal) and automatic VBACKUP switchover. `EVI`
(event input, unused) is tied to GND; `CLKOUT` (programmable clock output,
unused) is left NC; `INT#` (alarm) is pulled up 10k to `+3V3_AUX` and exposed as
`RTC_INT_N`.

**RTC backup cell — rechargeable ML1220.** `BT1` (KH-CR1220-2 holder, fits 12.5 mm
cells) carries a rechargeable Mn-Li ML1220 for a maintenance-free RTC; firmware
enables the RV-3028 internal trickle charger (TCE + ~3k series) so the cell tops
up whenever the board is powered. Do NOT fit a primary CR1220 (it would be
charged) or a LIR Li-ion (its 4.2 V charge target exceeds the 3.3 V supply). The
VBACKUP decap rule is waived on `V_RTC_BAT` (the RV-3028 regulates internally; a
cap on the cell net is optional and not fitted) — keyed on the net, not the ref,
so `U2.VDD` stays under the decap rule.

**Supervisor + watchdog — `TPS3823-33` @ U3.** The `-33` variant monitors a 3.3 V
rail (reset threshold VIT- = 2.93 V), so it must stay on `+3V3_AUX`. `MR#`
(manual reset) is left to the internal pull-up (de-asserted). `WDI` is fed from
`WATCHDOG_KICK` through a 1k series resistor (limits ESD back-feed when the rail
is off but the PL still drives); a floating WDI disables the watchdog timer.
`RESET#` is a push-pull active-low output to a PL bank-33 input.

**Watchdog safety — no reset during power-up.** Three independent guards, any one
of which alone prevents a power-up reset:
1. `U3.VDD` is `+3V3_AUX`, which defaults OFF — the supervisor is physically
   unpowered through power-up.
2. The TPS3823 disables its watchdog when WDI floats; WDI is driven only by the
   PL (`WATCHDOG_KICK`), Hi-Z until the fabric is configured.
3. `RESET#` gates no rail or POR line — it rides `WATCHDOG_RST_N` to a PL bank-33
   IO as a firmware-mediated event; a bite cannot hard-reset the board.

**Watchdog voltage domain.** Both watchdog nets are homed on bank-33 (+3V3 VCCO,
LVCMOS33) so U3's 3.3 V push-pull I/O stays in its own domain: `RESET#` drives a
3.3 V-VCCO input (no Zynq input-clamp forward-biasing, no series R needed), and
the LVCMOS33 `WDI` drive (VOH ~3.0 V) clears the TPS3823 WDI threshold
VIH = 0.7·VDD = 2.31 V. The reset-RC design rule is waived on `WATCHDOG_RST_N`:
it is a push-pull supervisor output driving a logic-event input, not a POR line,
so no pull-up and no RC cap are fitted (the PL internal pull holds the line while
`+3V3_AUX` is OFF).

**I2C address map (7-bit, whole carrier).**

| addr | device | sheet | bus segment |
|------|--------|-------|-------------|
| 0x20 | TCA9535  | bringup_rails | STM32_I2C2 trunk (always-on) |
| 0x22 | FUSB302B | usb_pd        | STM32_I2C2 trunk (always-on) |
| 0x40–0x41 | INA3221 | power_mon  | STM32_I2C2 trunk (always-on) |
| **0x51** | **ID-EEPROM (A0=1, A1=0)** | **board_services** | **AUX_I2C (gated)** |
| **0x52** | **RV-3028 RTC** | **board_services** | **AUX_I2C (gated)** |

No collisions. The QWIIC/STEMMA-QT connector that re-exports `+3V3_AUX` and
`AUX_I2C` (with ESD protection) lives on `board_qwiic`.

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| U1  | ID-EEPROM, EUI-48 MAC, 0x51 | `24AA025E48T-I_OT` | parts lib |
| U2  | RTC, 32.768 kHz DTCXO, 0x52 | `RV-3028-C7-32.768kHz-1ppm-TA-QC` | parts lib |
| U3  | supervisor + watchdog, 3.3 V | `TPS3823-33DBVR` | parts lib |
| BT1 | 12.5 mm coin-cell holder | `KH-CR1220-2` | parts lib |
| (decouple) | 100n | `Device:C` | C14663 |
| (R, WDI series) | 1k | `Device:R` | C21190 |
| (pullup, INT#) | 10k | `Device:R` | C25804 |

Each IC (U1.VCC / U2.VDD / U3.VDD) gets one 100n local bypass.

## Build & test

`test_board_services.py` checks model completeness, the decap/strap slice,
ratings, the SPICE-passive match, and the address/part invariants offline.

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/board_services/test_board_services.py -q
```

The board-level gates (full power tree, board ERC, cross-sheet I2C pull-up and
link/port-driver graph) stay aggregated by `schgen board`.
