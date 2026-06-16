# lcd — carrier ADAPTER for the reusable LCD + backlight subsystem

The carrier-specific GLUE for the 40-pin TTL RGB888 panel + SY7201 backlight
boost + capacitive-touch I2C. This is a **THIN ADAPTER**: the portable circuit
(netlist + SPICE + local test + design notes) lives ONCE in the project-agnostic
library package and this folder only BINDS it to the Zynq carrier's real net
names via the standard `META` contract.

> Library subsystem (the authoritative netlist + datasheet design notes):
> [`../../../subsystems/lcd/README.md`](../../../subsystems/lcd/README.md)

## Package contents

| file | role |
|------|------|
| `lcd.py`       | the ADAPTER — `from subsystems.lcd import lcd as _lib`, the `META` bind contract, `circuit()` returns `_lib.circuit(META)` |
| `__init__.py`  | re-exports `circuit`, `META` |
| `lcd.cir`      | THIN carrier subckt — the carrier external nets as pins, instantiating the library `subsystems/lcd/lcd.cir` |
| `test_lcd.py`  | bind-parity guard — adapter nets == `_lib.circuit(META)` nets, carrier names present, no abstract leak |
| `README.md`    | this file |

## The carrier bind (`META`)

The adapter binds the library's abstract interface to the carrier's REAL net
names; the rationale for each is in the `lcd.py` module docstring
(`carrier/research/lcd_backlight.md`). Summary:

| library abstract net | carrier net | why |
|----------------------|-------------|-----|
| `+VBOOST_IN`    | `+5V_LCD`   | gated 5V module rail feeding the SY7201 boost |
| `+VDD_LCD`      | `+3V3_LCD`  | gated 3.3V panel-logic + touch rail |
| `+VDD_TP_CLAMP` | `+3V3`      | always-on touch-I2C ESD clamp reference |
| `LCD_R0..B7`, `LCD_DISP/HSYNC/VSYNC/DE`, `LCD_PCLK` | identity | PL bank-34 TTL panel video/control (J3) |
| `BL_PWM`        | `LCD_BL_PWM`| backlight EN/PWM |
| `TP_SDA/SCL`    | `LCD_CTP_SDA/SCL` | capacitive-touch I2C (carrier `LCD_CTP` bus) |
| `TP_RST/INT`    | `LCD_CTP_RST/INT` | touch reset / interrupt |
| `GND`           | `GND`       | identity |

`META["expects"]` declares the linker deferral for the ports that bind on the
generated SoM-connector sheets (panel video/control + `BL_PWM` on J3 bank 34;
the touch group on J2 bank 13); `META["buses"]` names the touch I2C the carrier
`LCD_CTP` bus; `META["notes"]` restores the carrier's power-tree draw prose.

Because the adapter is a pure rename of the library circuit, the emitted
`carrier/schematic/lcd.kicad_sch` and its golden render are **byte-identical** to
the pre-folding flat adapter.

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/lcd/test_lcd.py -q
```

The library's full electrical correctness (decap / boost topology / ratings /
SPICE) is proven by `subsystems/lcd/test_lcd.py`; the board-level gates (power
tree, ERC, link/port-driver graph, netlist merge) stay aggregated by
`schgen board`.
