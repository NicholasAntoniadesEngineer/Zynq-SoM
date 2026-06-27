# lcd — 40-pin TTL RGB888 panel + SY7201 backlight boost + touch I2C

A project-agnostic, reusable schgen subsystem driving a 40-pin 0.5 mm TTL RGB888
FFC display (Innolux AT043TN24-lineage pinout; 4.3"–7" 480×272 / 800×480 class)
on the Zynq-7000 SoM carrier. It bundles the 24-bit RGB + sync panel port, an
on-board Silergy SY7201 constant-current backlight boost, and a capacitive-touch
I2C group clamped by a low-cap ESD array — capacitive touch arriving through the
same 40-pin connector (no extra tail). It declares its interface as abstract
port/rail names and knows nothing about any board; a consuming project supplies a
bind map to drop it onto real nets.

## Interface

A consuming project calls `lcd.circuit(meta)` with the standard `Meta` adapter
dict. Rails classify as POWER/GROUND by name (the `+` prefix and `GND`), so a
standalone build and a bound build share net classes.

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VBOOST_IN`    | POWER  | boost input (5 V class) → SY7201 IN, L1, input bulk. Supply a **gated** rail so the backlight boost is fully off when the module is down. |
| `+VDD_LCD`      | POWER  | panel logic + touch supply (3.3 V class). Supply a **gated** rail so a powered-down panel is not back-fed through its DISP / touch pull-ups (they land here). Panel-VDD bypass 10u + 100n on this rail. |
| `+VDD_TP_CLAMP` | POWER  | **always-on** rail referencing the USBLC6 touch-I2C ESD clamp (VBUS pin). Separate from `+VDD_LCD` so ESD protection is valid even when the gated panel rail is off. |
| `GND`           | GROUND | ground (FFC grounds + boost / ISET return + clamp ref). |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `LCD_R0..R7`, `LCD_G0..G7`, `LCD_B0..B7` | single | 24-bit TTL RGB888 data bus (FFC pins 5–12 / 13–20 / 21–28). |
| `LCD_PCLK`  | single | pixel clock (~33 MHz), through a **22R source-series** damping resistor (R7) at the host end → FFC pin 30. |
| `LCD_HSYNC`, `LCD_VSYNC`, `LCD_DE` | single | timing / sync (FFC pins 32 / 33 / 34). |
| `LCD_DISP`  | single | display on/off (FFC pin 31); **10k pull-up to `+VDD_LCD`** (R6) → default ON when the rail is gated up. |
| `BL_PWM`    | single | SY7201 EN/PWM backlight enable; **100k pull-down** (R4) → default OFF until the host drives it. |
| `TP_SDA`, `TP_SCL` | i2c (bus `LCD_CTP`, 400 kHz) | capacitive-touch I2C; open-drain, **4k7 pull-ups to `+VDD_LCD`** (R2 / R3). Brought through the USBLC6 array (FFC 37 / 38 on the unprotected side). |
| `TP_RST`    | single | touch reset (FFC pin 39); **100k pull-down** (R5) → held in reset until the host releases it (a GPIO-driven reset, not an RC reset). |
| `TP_INT`    | single | touch interrupt (FFC pin 40); **no pull** — GT911-class controllers sample INT at reset release to select the I2C address; FT5206-class treats it as a plain output. |

### Binding it from a project

```python
from subsystems.lcd import lcd

META = {
    "bind": {
        "+VBOOST_IN": "+5V_LCD", "+VDD_LCD": "+3V3_LCD",
        "+VDD_TP_CLAMP": "+3V3", "GND": "GND",
        "LCD_R0": "LCD_R0", ...,        # RGB/sync/PCLK (identity on the carrier)
        "BL_PWM": "LCD_BL_PWM",
        "TP_SDA": "LCD_CTP_SDA", "TP_SCL": "LCD_CTP_SCL",
        "TP_RST": "LCD_CTP_RST", "TP_INT": "LCD_CTP_INT",
    },
    "expects": {"LCD_R0": "som_j3 (bank 34)", "TP_SDA": "som_j2 (bank 13)", ...},
    "buses": {"i2c": "LCD_CTP"},                          # touch-I2C bus group
    "notes": {"draws_lcd": "...", "draws_boost": "..."},  # power-tree draw notes
}

def circuit():
    return lcd.circuit(META)
```

`bind` rebinds every externally-visible net (POWER/GROUND/PORT only) in place,
order-preserving — a SIGNAL net like the boost switch node is private wiring and
is never rebound. `expects` attaches a linker deferral declaring which project
sheet binds each port. `buses` / `notes` let a project supply its own touch-I2C
bus name and power-tree draw prose. The carrier adapter is
`carrier/subsystems/lcd.py`. Internal SIGNAL nodes are private and never
bindable: `LCD_BL_SW` (boost switch), `LCD_VLED_P` (boost output / OVP sense),
`LCD_VLED_N` (LED-string return / FB current sense), `LCD_PCLK_PANEL`
(post-damping PCLK), and `CTP_SDA_FFC` / `CTP_SCL_FFC` (unprotected touch nodes).
FFC pins 35 (panel NC) and 41 / 42 (shell tabs) are explicit author no-connects.

## Design

**40-pin FFC pinout.** Follows the de-facto 40-pin 0.5 mm convention for the
4.3"–7" 480×272 / 800×480 class: 1 `VLED-`, 2 `VLED+`, 3 / 29 / 36 `GND`,
4 `VDD` (3.3 V), 5–12 `R0..R7`, 13–20 `G0..G7`, 21–28 `B0..B7`, 30 `PCLK`,
31 `DISP`, 32 `HSYNC`, 33 `VSYNC`, 34 `DE`, 35 `NC`, 37–40 the capacitive-touch
group. The connector is the JUSHUO AFC07-S40FCA-00 (J1); its bare-number pins
stay numeric and the netlist gate proves KiCad sees every pad.

**Backlight boost (SY7201ABC, U1).** SOT-23-6 constant-current WLED boost driver
(VIN 2.5–30 V, VREF(FB) = 200 mV, 2 A switch limit, 1 MHz, open-LED OVP clamp
typ 30 V, EN abs-max 4 V so 3.3 V logic drives it directly). Topology:
`+VBOOST_IN` → L1 (10 µH) → LX, SS34 catch diode (D1) from LX → `VLED+`, output
cap on `VLED+`, OVP senses `VLED+`, and FB ties the LED-string return (`VLED-`)
and the ISET resistor. **I_LED = 0.2 V / R_ISET = 0.2 / 1.5R = 133 mA** (R1),
inside the 125–150 mA window for the 7" 800×480 class (~9.6 V string). At 5 V in
→ ~9.6 V / 133 mA out, the peak inductor current (~0.43 A) leaves >4× margin to
both the 2 A switch limit and the SWPA4030 inductor's ~1.95 A Isat. D1
orientation is enforced: cathode (D1.1, K) on the boost output, anode (D1.2, A)
on the LX switch node.

**Boost output cap (C2, 2.2 µF / 50 V X7R).** Sized above the datasheet 1 µF:
at the 9–25 V output the X7R DC-bias derating eats over half of a 1 µF, so
2.2 µF keeps real capacitance and loop margin healthy. The 50 V rating survives
the 30 V open-LED OVP clamp; the SS34 (40 V) survives it too. The CAP_VOLTAGE
2×-DC-bias derate (which would demand 60 V) is **waived** in the netlist because
the 30 V is a rare open-LED fault transient, not a continuous bias — the
continuous string is ~9.6 V (50 V/2 = 25 V derated ≫ 9.6 V).

**Input decoupling.** `+VBOOST_IN` carries a 10 µF bulk (C1) plus a dedicated
1 µF HF ceramic (C8, 50 V) at the SY7201 IN pin. The gated `+VDD_LCD` panel rail
carries a 100 nF (C3) plus a 10 µF bulk (C7).

**Touch I2C ESD + pull-ups.** The FFC is user-touchable, so the touch-I2C pair
is clamped at the connector by a USBLC6-2SC6 (U2; 1↔6 / 3↔4 passthrough): the
external FFC pins (37 / 38) land on the unprotected side (`CTP_*_FFC`), the
protected pair drives the pull-ups and the host. The clamp references the
always-on `+VDD_TP_CLAMP` so protection is valid even when the gated `+VDD_LCD`
rail is off. The open-drain bus requires the **4k7 pull-ups to `+VDD_LCD`**
(R2 / R3) — it is dead without them.

**Safe defaults.** `DISP` has a 10k pull-up (panel on when the rail comes up and
the host is unconfigured); `BL_PWM` a 100k pull-down (backlight off until
driven); `TP_RST` a 100k pull-down (touch held in reset until released).
`TP_INT` carries no pull so a GT911-class controller's reset-time address-select
is not forced. The `TP_RST` reset is GPIO-driven, so the design-rule RC-reset
check is **waived** (no cap-to-GND by design).

**Power-tree draws.** `+VDD_LCD` declares 0.100 A (panel logic + touch);
`+VBOOST_IN` declares 0.450 A (boost input at the 133 mA LED string plus
margin).

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J1 | AFC07-S40FCA-00 | 40P 0.5 mm FFC connector | (parts lib) |
| U1 | SY7201ABC | boost WLED driver, SOT-23-6 | (parts lib) |
| L1 | 10uH | SWPA4030S100MT power inductor | (parts lib) |
| U2 | USBLC6-2SC6 | low-cap ESD array (touch I2C) | (parts lib) |
| D1 | SS34 | Device:D_Schottky, D_SMA | C8678 |
| R1 | 1.5R | Device:R, 0603 (ISET 133 mA) | C22769 |
| C1 | 10u | Device:C, 0805 (boost input bulk) | C15850 |
| C2 | 2.2u | Device:C, 0805 (boost output, 50 V) | C125847 |
| C3 | 100n | Device:C, 0603 (panel VDD decoupling) | C14663 |
| C7 | 10u | Device:C, 0805 (panel VDD bulk) | C15850 |
| C8 | 1u | Device:C, 0603 (boost input HF, 50 V) | C15849 |
| R2, R3 | 4k7 | Device:R, 0603 (touch I2C pull-ups) | C23162 |
| R4 | 100k | Device:R, 0603 (BL_PWM pull-down) | C25803 |
| R5 | 100k | Device:R, 0603 (TP_RST pull-down) | C25803 |
| R6 | 10k | Device:R, 0603 (DISP pull-up) | C25804 |
| R7 | 22R | Device:R, 0603 (PCLK damping) | C23345 |

C7 / C8 take auto-assigned refs (`auto_ref`); the values shown follow the J1/U1
fixed assignments above.

## Build & test

`test_lcd.py` runs the subsystem-local slices offline — abstract interface
(incl. the internal SIGNAL boost nodes), model completeness (every pin
netted-or-NC, the three FFC no-connects), decoupling / I2C / reset completeness,
the backlight boost topology, part-rating + cap-derate coverage (incl. the C2
OVP-clamp waiver), the SPICE-subckt ↔ netlist passive match, and the bind
contract.

```bash
PYTHONPATH=. python3 -m pytest subsystems/lcd/test_lcd.py -q
```
