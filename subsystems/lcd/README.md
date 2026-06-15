# lcd — 40-pin TTL RGB888 panel + SY7201 backlight boost + touch I2C (reusable subsystem)

A project-agnostic, self-contained schgen subsystem: a de-facto **40-pin 0.5 mm
TTL RGB888 FFC** panel port (Innolux AT043TN24-lineage pinout) with an on-board
**Silergy SY7201ABC** constant-current backlight **boost** and a **capacitive-
touch I2C** group clamped by a USBLC6-2SC6 ESD array. It declares its interface
as **abstract** port + rail names and knows nothing about any board; a consuming
project supplies a **bind map** (`abstract -> real net`) to drop it onto real
nets. Same `subsystems/<name>/` library layout as the exemplar
`subsystems/usb_pd/`.

## Package contents

| file | role |
|------|------|
| `lcd.py`      | the NETLIST — `circuit(meta=None)`, abstract ports/rails |
| `lcd.cir`     | SPICE subckt — the passive network (boost + bypass + pulls + clamp) with abstract ports as subckt pins |
| `test_lcd.py` | LOCAL electrical-correctness test (offline, runs the board gate slices on just this subsystem) |
| `README.md`   | this file |

Active parts are **referenced, never vendored**: the AFC07-S40FCA-00 FFC, the
SY7201ABC boost, the SWPA4030S100MT inductor and the USBLC6-2SC6 ESD array all
source their symbol/footprint/MPN/LCSC from the global `parts/` library. The
FFC connector's bare-number pins stay numeric; the netlist gate proves KiCad
sees every FFC pad.

## The abstract interface (the reuse contract)

A consuming project binds these names. Rails classify as POWER/GROUND by name
(the `+` prefix + `GND`), exactly as real board rails do, so a standalone build
and a bound build share net classes.

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VBOOST_IN`    | POWER  | boost-converter input (5 V class) -> SY7201 IN / L1 / input bulk. Supply a **gated** rail so the backlight boost is fully off when the module is down. |
| `+VDD_LCD`      | POWER  | panel logic + touch supply (3.3 V class). Supply a **gated** rail so a powered-down panel is not back-fed through its DISP / touch pull-ups (they land on this rail). Panel-VDD bypass 10u + 100n here. |
| `+VDD_TP_CLAMP` | POWER  | **always-on** rail referencing the USBLC6 touch-I2C ESD clamp (VBUS pin). Kept separate from `+VDD_LCD` so ESD protection is valid even when the gated panel rail is off. |
| `GND`           | GROUND | ground (FFC grounds + boost / ISET return + clamp ref). |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `LCD_R0..R7`, `LCD_G0..G7`, `LCD_B0..B7` | single | 24-bit TTL RGB888 data bus (LSB→MSB per colour). |
| `LCD_PCLK`  | single | pixel clock (~33 MHz at 800×480@60), through a **22R source-series** damping resistor (R7). |
| `LCD_HSYNC`, `LCD_VSYNC`, `LCD_DE` | single | timing / sync. |
| `LCD_DISP`  | single | display on/off; **10k pull-up to `+VDD_LCD`** → default ON when the rail is gated up. |
| `BL_PWM`    | single | SY7201 EN/PWM backlight enable; **100k pull-down** → default OFF (boost off until the host drives it). |
| `TP_SDA`, `TP_SCL` | i2c (bus `LCD_CTP`, 400 kHz) | capacitive-touch I2C; open-drain, **4k7 pull-ups to `+VDD_LCD`** here. Brought through the USBLC6 ESD array (FFC 37/38 on the unprotected side). |
| `TP_RST`    | single | touch reset; **100k pull-down** → held in reset until the host releases it (a GPIO-driven reset, **not** an RC reset). |
| `TP_INT`    | single | touch interrupt; **no pull** — GT911-class controllers sample INT at reset release to select the I2C address (low→0x5D, high→0x14); FT5206-class (0x38) treats it as a plain output. |

Internal **SIGNAL** wiring (private, never bindable — kept verbatim): the boost
switch node `LCD_BL_SW`, the boost-output / OVP-sense node `LCD_VLED_P`, the
LED-string return / FB current-sense node `LCD_VLED_N`, the post-damping pixel-
clock node `LCD_PCLK_PANEL`, and the unprotected-side touch nodes `CTP_SDA_FFC`
/ `CTP_SCL_FFC`.

FFC pin 35 (panel NC) and the two shell-tab pins 41/42 are explicit author
no-connects.

### Parts (from the global `parts/` lib + inline passives)

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J1 | AFC07-S40FCA-00 | 40P 0.5 mm bottom-contact FFC | C262572 |
| U1 | SY7201ABC | boost WLED driver, 30 V/2 A/1 MHz, SOT-23-6 | C82173 |
| L1 | 10uH | SWPA4030S100MT power inductor (Isat ≈ 1.1 A) | C38117 |
| D1 | SS34 | Schottky 40 V/3 A SMA catch diode | C8678 |
| U2 | USBLC6-2SC6 | low-cap ESD array on the touch I2C | C7519 |
| C1 | 10u | boost input bulk | C15850 |
| C2 | 2.2u | boost output (50 V X7R, LCD-1) | C125847 |
| C3 | 100n | panel VDD decoupling | C14663 |
| C4 | 10u | panel VDD bulk | C15850 |
| R1 | 1.5R | ISET (I_LED = 0.2 V / R = 133 mA) | C22769 |
| R2, R3 | 4k7 | touch I2C pull-ups | C23162 |
| R4, R5 | 100k | BL_PWM + TP_RST pull-downs | C25803 |
| R6 | 10k | DISP pull-up | C25804 |
| R7 | 22R | PCLK source-series damping | C23345 |

## Consuming it from a project

A project supplies a thin adapter declaring ONE standard `META` dict (the
adapter contract, `schgen.core.subsystem.Meta`) and forwards it:

```python
from subsystems.lcd import lcd

META = {
    # abstract subsystem net -> your real board net
    "bind": {
        "+VBOOST_IN": "+5V_LCD", "+VDD_LCD": "+3V3_LCD",
        "+VDD_TP_CLAMP": "+3V3", "GND": "GND",
        "LCD_R0": "LCD_R0", ...,        # RGB/sync/PCLK (identity on the carrier)
        "BL_PWM": "LCD_BL_PWM",
        "TP_SDA": "LCD_CTP_SDA", "TP_SCL": "LCD_CTP_SCL",
        "TP_RST": "LCD_CTP_RST", "TP_INT": "LCD_CTP_INT",
    },
    # optional: tell the linker which of your sheets binds a deferred port
    "expects": {"LCD_R0": "som_j3 (bank 34)", "TP_SDA": "som_j2 (bank 13)", ...},
    # optional house-style overrides (keep your derived artifacts byte-stable)
    "buses": {"i2c": "LCD_CTP"},                       # the touch-I2C bus group
    "notes": {"draws_lcd": "...", "draws_boost": "..."},  # power-tree draw notes
}

def circuit():
    return lcd.circuit(META)
```

The four standard `META` keys (`bind` / `expects` / `buses` / `notes`) are
universal across every reusable subsystem — a typo'd top-level key is a hard
`CircuitError`, never silently dropped. `bind` renames every external **in
place, order-preserving** (POWER/GROUND/PORT only — a SIGNAL net like the boost
switch node is private wiring and is never rebound; a SIGNAL key or a collision
is a hard `CircuitError`). Because the rename preserves net insertion order,
parts, refs, NCs, port-type payloads and the TestPoint VALUE text, **binding to
the exact names a hand-written sheet used yields a byte-identical emitted
sheet.** The carrier adapter is `carrier/subsystems/lcd.py`.

## Design notes (datasheet + reference-design contract)

- **The de-facto 40-pin pinout.** The dominant 40-pin 0.5 mm convention for the
  4.3"–7" 480×272 / 800×480 class (Innolux AT043TN24 V.7 lineage; HAOYU HY7-LCD
  / HY070CTP-A, Adafruit #2353, SSD1963/RA8875 boards): 1 `VLED-`, 2 `VLED+`,
  3/29/36 `GND`, 4 `VDD` (3.3 V), 5–12 `R0..R7`, 13–20 `G0..G7`, 21–28 `B0..B7`,
  30 `PCLK`, 31 `DISP`, 32 `HSYNC`, 33 `VSYNC`, 34 `DE`, 35 `NC`, 37–40 the
  capacitive-touch group `CTP-SDA / CTP-SCL / CTP-RST / CTP-INT`. Capacitive
  touch comes **through the same 40-pin connector** — no extra tail. Resistive
  panels are NOT supported (no ADC on those nets).
- **Backlight boost (SY7201ABC, datasheet rev 0.4).** SOT-23-6: 1 `LX`, 2 `GND`,
  3 `FB`, 4 `EN/PWM`, 5 `OVP`, 6 `IN`. VIN 2.5–30 V, VREF(FB) = 200 mV, 2 A
  switch limit, 1 MHz fixed, open-LED OVP clamp typ 30 V, EN abs-max 4 V (3.3 V
  logic direct), PWM dimming ≥ 20 kHz. Topology: `+VBOOST_IN` → L1 10uH → `LX`,
  catch diode SS34 `LX` → `VLED+`, output cap on `VLED+`, `OVP` senses `VLED+`,
  `FB` ties the LED-string return (`VLED-`) and the ISET resistor.
  **I_LED = 0.2 V / R_ISET = 0.2 / 1.5R = 133 mA** — inside the 125–150 mA
  window for the 7" 800×480 class (~9.6 V string). Operating point (5 V in →
  9.6 V/133 mA out): D ≈ 0.52, Iin ≈ 0.30 A, inductor ripple ~0.26 A p-p, peak
  ~0.43 A — 4.6× margin to the 2 A switch limit, 2.5× to the 1.1 A Isat.
- **LCD-1 (output cap).** The boost output cap is **2.2 µF / 50 V X7R**
  (C125847), not the datasheet 1 µF. At the 9–25 V output the X7R DC-bias
  derating eats well over half of a 1 µF; 2.2 µF keeps real capacitance and
  ripple/loop margin healthy while staying 50 V-rated to survive the **30 V
  open-LED OVP clamp** transient. The CAP_VOLTAGE 2×-DC-bias derate (which would
  demand 60 V) is **waived**: the 30 V is a rare open-LED fault clamp, not a
  continuous bias — the continuous string is ~9.6 V (50 V/2 = 25 V derated ≫
  9.6 V). The SS34 (40 V) and the C2 (50 V) both survive the clamp.
- **Touch I2C ESD + pull-ups.** The FFC is user-touchable, so the touch-I2C pair
  is clamped at the connector by a **USBLC6-2SC6** low-cap ESD array (1↔6 / 3↔4
  passthrough): the external FFC pins land on the unprotected side
  (`CTP_*_FFC`), the protected pair drives the pull-ups + the host. The clamp
  references the **always-on** `+VDD_TP_CLAMP` so protection is valid even when
  the gated `+VDD_LCD` panel rail is off. The touch bus is open-drain → **4k7
  pull-ups to `+VDD_LCD`** are mandatory (the bus is dead without them).
- **Safe defaults.** `DISP` has a **10k pull-up** (panel on when the rail comes
  up and the host is unconfigured); `BL_PWM` a **100k pull-down** (backlight off
  until driven); `TP_RST` a **100k pull-down** (touch held in reset). `TP_INT`
  carries **no pull** so a GT911-class controller's reset-time address-select is
  not forced. The `TP_RST` reset is GPIO-driven, **not** an RC reset, so the
  design-rule reset check is **waived** (no cap-to-GND by design).
- **PCLK damping.** PCLK (~33 MHz, the highest edge-rate line) goes through a
  **22R source-series** resistor at the source/host end (R7) → FFC pin 30.

## Local test vs board gates

`test_lcd.py` runs the **subsystem-local** slices offline: declared abstract
interface (incl. the verbatim internal SIGNAL boost nodes), model completeness
(every pin netted-or-NC, the three intentional FFC no-connects), decoupling /
I2C / reset completeness (the touch pull-ups land here so the I2C-pull-up rule
is exercised; the GPIO-driven TP_RST reset waiver is honoured), the backlight
boost topology (input bulk, 50 V output cap on the OVP-sense node, the 1.5R ISET
sense, inductor + catch diode), part-rating coverage + per-rail cap derating
(incl. the C2 OVP-clamp clearance), the SPICE-subckt ↔ netlist passive match,
and the bind contract. **Cross-board** gates stay aggregated at board level and
are *not* duplicated here: the link / port-driver graph (which sheet binds each
RGB/sync/touch line), the full power-tree headroom, board ERC, and the board
netlist merge — all run by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/lcd/test_lcd.py -q
```
