# bringup_rails — bring-up control surfaces (DIPs, override expander, buttons)

The human and software control surfaces that drive the carrier's staged
bring-up. The bring-up contract is "DIP is the master, STM32 is a veto": the
rail/module DIP switches request enables, the TCA9535 I2C expander lets the
STM32 system controller veto them, and the EN AND-gate cells (on `bringup_en` /
`bringup_en_modules`) consume both. This sheet carries the masters, the veto
expander, the user/reset buttons, and the config straps that feed those cells.

This is a carrier-local subsystem: it uses real carrier net names directly, has
no abstract `bind` map, and is foldered only for 4-artifact parity with the
generic `subsystems/<name>/` library.

## Interface

Carrier nets driven by `circuit()`:

| net | role |
|-----|------|
| `+3V3_SC` | POWER — DIP bus, TCA9535 VCC, all I2C/INT pull-ups. SoM system-controller rail, alive from default 5 V VBUS before any carrier rail. |
| `+3V3` | POWER — user-button pull-ups (PL bank VCCO). |
| `GND` | GROUND. |
| `BU_DIP_*` (14) | PORT — DIP A-inputs → `bringup_en` / `bringup_en_modules`. |
| `BU_OVR_*` (11) | PORT — TCA9535 veto/driver lines → the EN cells. |
| `STM32_I2C2_SDA` / `STM32_I2C2_SCL` | PORT — i2c bus `STM32_I2C2`, 400 kHz, shared with the FUSB302. |
| `SC_INT_N` | PORT — single SC interrupt, wire-OR of the TCA9535 and FUSB302 INT. |
| `PMON_ALERT_N`, `USBOTG_FLT_N`, `PD_FLT_N` | PORT — telemetry flags read in as expander inputs. |
| `PL_BTN0` / `PL_BTN1` | PORT — user buttons to PL bank-33 pins. |
| `STM32_NRST` | PORT — reset button (J3.47). |
| `PUDC_34` | PORT — bank-34 PUDC config strap (J3.39). |

Pull-ups / straps this sheet owns:

| net | pull | rail |
|-----|------|------|
| `STM32_I2C2_SCL`, `STM32_I2C2_SDA` | 4k7 | `+3V3_SC` |
| `SC_INT_N` (U1.INT#) | 10k | `+3V3_SC` |
| `BU_OVR_LCD_BL` (U1.P10) | 100k pulldown | GND |
| `BU_P16`, `BU_P17` (U1.P16/P17 spare) | 100k | GND |
| `PL_BTN0`, `PL_BTN1` | 10k | `+3V3` |
| `PUDC_34` | 10k | GND |

## Design

**SW1 (DSHP04TSGER) — rail DIP.** Silkscreen positions 1=+5V, 2=+3V3, 3=+1V8,
4=USER_LED. Odd pins (1/3/5/7) bus to `+3V3_SC`; flipping a position pulls that
rail's cell A-input (`BU_DIP_5V0` / `BU_DIP_3V3` / `BU_DIP_1V8` /
`BU_DIP_USER_LED`) high. The 100k pulldowns live at the gates. DSHP04 pairing is
position n = pins (n, 9-n), so the signal nets land on even pins 8/2/6/4.

**SW2 (DSHP08TSGER) — module DIP.** Positions 1=HDMI_TX, 2=HDMI_RX, 3=LCD,
4=CAM, 5=SD, 6=USB, 7=PMOD, 8=spare (an `EN_LCD_BL` provision). The DSHP08
bottom row numbers 9..16 left-to-right, so each rocker bridges pins (n, n+8) in
the same column — a straight pairing, not the DSHP04 diagonal. The top row 1-8
carries `+3V3_SC`; the bottom-row pin carries the `BU_DIP_*` module-enable net.

**SW6 (DSHP04TSGER) — extension DIP.** Positions 1=HDMI_TX_5V, 2=LCD_5V
(`BU_DIP_HDMI_TX_5V` / `BU_DIP_LCD_5V`), gating the +5V_HDMI_TX and +5V_LCD
module rails; positions 3/4 are spare. A separate DIP is used rather than
overloading SW1/SW2, both of which are fully allocated. Same DSHP04 pairing as
SW1 (signals on even pins 8/2); the spare even pins `SW6.4`/`SW6.6` are author
no-connects (the odd `+3V3_SC` bus already covers all four positions, so a
future gate only adds a `BU_DIP` port).

**U1 (TCA9535PWR @ 0x20) — STM32 override expander.** A0=A1=A2=GND set address
0x20; the FUSB302B at 0x22 shares the bus with no clash. POR state is all-inputs,
so with the cells' 100k pull-ups the design defaults to DIP control — a blank
system controller still boots "switches only". The TCA9535 has no internal port
pulls (unlike the PCA9555), so every floating port is resolved explicitly:

- P00..P07 → the eight module veto lines `BU_OVR_HDMI_TX … BU_OVR_USER_LED`.
- P10 → `BU_OVR_LCD_BL`, the LCD-backlight provision driver, with a 100k
  pulldown here so the spare cell stays OFF until software raises it.
- P11 → `PMON_ALERT_N` (input; INA3221 wire-OR, pull-up on `power_mon`).
- P12/P13 → `BU_OVR_HDMI_TX_5V` / `BU_OVR_LCD_5V` (their 100k pull-ups live at
  the gates on `bringup_en_modules`, like P00..P07).
- P14 → `USBOTG_FLT_N` (input; TPS2051C fault, pull-up to `+3V3_SC` on
  `usbc_otg` — a +5V level would break the TCA9535 VCC+0.5 V abs-max).
- P15 → `PD_FLT_N` (input; TPS26631 inlet-eFuse fault, pull-up on `pd_input`).
- P16/P17 → spare, each 100k to GND so they cannot float.
- SCL/SDA → `STM32_I2C2` with 4k7 pull-ups to `+3V3_SC`; the bus must live
  before any carrier rail (PD negotiation precedes every rail).
- INT# → `SC_INT_N`, open-drain, wire-OR with the FUSB302 INT onto the single SC
  interrupt; this sheet owns the one 10k pull-up to `+3V3_SC` for the merged net.

**Buttons (TS-1187A-B-A-B).** Pads 1/2 and 3/4 are internally bridged pairs.
Two user buttons drive `PL_BTN0` / `PL_BTN1` to PL bank-33 pins: active-LOW with
a 10k pull-up to `+3V3` (the PL bank VCCO) and a 100n cap across the contacts for
RC debounce. The reset button drives `STM32_NRST` (J3.47) with a 100n cap; the
STM32's internal ~40k pull-up means no external resistor is needed.

**PUDC strap.** `PUDC_34` (bank-34 IO_L3P_PUDC, J3.39) has no resistor on the
SoM, so a 10k to GND is added here. PUDC LOW during config enables the Zynq
internal pull-ups, which is friendly to the LCD "DISP defaults on" net and the
active-low PL buttons. The strap is a carrier-side part placed on this surface
sheet and bound to J3.

**Power budget.** `+3V3_SC` draws ~5 mA (TCA9535 plus the closed-DIP pull
currents and the I2C/INT pull-ups when sinking); `+3V3` draws ~1 mA from the two
button pull-ups when pressed. `+3V3_SC` and both shared I2C lines have
testpoints, as this sheet owns the bus pull-ups.

## Parts

| ref | value | lib/part | LCSC |
|-----|-------|----------|------|
| SW1 | — | DSHP04TSGER | — |
| SW2 | — | DSHP08TSGER | — |
| SW6 | — | DSHP04TSGER | — |
| U1 | — | TCA9535PWR | — |
| SW3, SW4, SW5 | — | TS-1187A-B-A-B | — |
| C1 | 100n | C decouple (U1.VCC) | C14663 |
| C (debounce ×3) | 100n | Device:C | C14663 |
| R (I2C pulls ×2) | 4k7 | Device:R | C23162 |
| R (INT pull) | 10k | Device:R | C25804 |
| R (button pulls ×2) | 10k | Device:R | C25804 |
| R (PUDC strap) | 10k | Device:R | C25804 |
| R (P10/P16/P17) | 100k | Device:R | C25803 |

DSHP04TSGER, DSHP08TSGER, TCA9535PWR, and TS-1187A-B-A-B come from the
project part library via `use_part`.

## Build & test

`test_bringup_rails.py` checks model completeness (including the `SW6.4`/`SW6.6`
NCs), rail/port classes, the design-rule slice (I2C pull-up, NRST RC, no
floating strap), the part/SPICE slices, and the surface invariants this sheet
owns: three DIPs, the TCA9535 @0x20, the 4k7 I2C pulls, the single 10k INT
pull-up, the P10/P16/P17 don't-float pulldowns, the 10k button pulls, the PUDC
10k-to-GND strap, and the SC-rail/I2C testpoints.

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/bringup_rails/test_bringup_rails.py -q
```
