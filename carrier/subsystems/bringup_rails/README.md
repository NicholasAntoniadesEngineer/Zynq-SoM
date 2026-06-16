# bringup_rails — bring-up control surfaces (carrier-local subsystem)

The human/software **control surfaces** the staged bring-up EN cells consume:
the rail/module DIP switches, the STM32 override I2C expander, and the user /
reset buttons (`carrier/research/bringup_power_gating.md` sections 1, 3.4, 3.5,
4). The EN AND-cells themselves live on `bringup_en` / `bringup_en_modules`;
this sheet provides what feeds them.

The staged contract is "**DIP is the master, STM32 is a veto**". This sheet
carries the master switches and the veto expander, plus the shared SC I2C bus
pull-ups and the board's single SC interrupt pull-up.

This is a **carrier-local** subsystem (real carrier net names, no abstract
interface / `bind` map); it is folded into a per-name package only for
4-artifact parity with the generic `subsystems/<name>/` library.

## What it carries

* **SW1 (DSHP04TSGER) — rail DIP.** Positions 1=+5V, 2=+3V3, 3=+1V8,
  4=USER_LED. The odd pins bus to `+3V3_SC`; the even pins are the cell A-inputs
  `BU_DIP_5V0/3V3/1V8/USER_LED` (the 100k pulldowns live at the gates).
* **SW2 (DSHP08TSGER) — module DIP.** Positions 1=HDMI_TX … 7=PMOD, 8=spare
  (`EN_LCD_BL` provision). A-inputs `BU_DIP_HDMI_TX … BU_DIP_PMOD`,
  `BU_DIP_SPARE`.
* **SW6 (DSHP04TSGER) — round-5 extension DIP.** Positions 1=HDMI_TX_5V,
  2=LCD_5V (`BU_DIP_HDMI_TX_5V` / `BU_DIP_LCD_5V`); positions 3/4 spare —
  even pins `SW6.4`/`SW6.6` are **author no-connects**.
* **U1 (TCA9535PWR @ 0x20, A0=A1=A2=GND)** — the STM32 override expander
  (FUSB302B at 0x22 shares the bus, no clash). POR = all-inputs, so with the
  cells' 100k pull-ups everything defaults to DIP control. Ports:
  - P00..P07 → the 8 module veto lines `BU_OVR_HDMI_TX … BU_OVR_USER_LED`.
  - P10 → `BU_OVR_LCD_BL`, the LCD-backlight provision driver, with a **100k
    pulldown here** (the spare cell is OFF until software raises it).
  - P12/P13 → round-5 veto lines `BU_OVR_HDMI_TX_5V` / `BU_OVR_LCD_5V`
    (their 100k pull-**ups** live at the gates on `bringup_en_modules`).
  - P11 → `PMON_ALERT_N` (INA3221 wire-OR, PU on `power_mon`).
  - P14 → `USBOTG_FLT_N` (TPS2051C fault, PU on `usbc_otg`).
  - P15 → `PD_FLT_N` (TPS26631 inlet-eFuse fault, PU on `pd_input`).
  - P16/P17 → spare, each a **100k to GND** "don't float" (the TCA9535 has no
    internal pulls, unlike the PCA9555).
  - SCL/SDA → `STM32_I2C2` with **4k7 pull-ups to +3V3_SC** (dossier R1: the
    bus must live before any carrier rail).
  - INT# → `SC_INT_N` (wire-OR with the FUSB302 INT, the board's single SC
    interrupt) with the **one 10k pull-up** for the merged net.
* **Buttons (TS-1187A-B-A-B).** Two user buttons → `PL_BTN0/1`, active-LOW,
  **10k to +3V3** (bank VCCO) + 100n debounce. The reset button → `STM32_NRST`
  (J3.47, internal ~40k pull-up, no external R) + 100n.
* **PUDC strap.** `PUDC_34` (bank-34 IO_L3P_PUDC) **10k to GND** — PUDC LOW
  during config enables the Zynq internal pull-ups (friendly to the LCD "DISP
  defaults on" + active-low buttons). Lives here, binds J3↔here.

## Rails / nets

| net | role |
|-----|------|
| `+3V3_SC` | POWER — DIP bus, TCA9535 VCC, all I2C/INT pull-ups. Always-on. |
| `+3V3` | POWER — user-button pull-ups (bank VCCO). |
| `GND` | GROUND. |
| `BU_DIP_*` (14) | PORT — DIP A-inputs → `bringup_en` / `bringup_en_modules`. |
| `BU_OVR_*` (11) | PORT — TCA9535 veto lines → the EN cells. |
| `STM32_I2C2_SDA/SCL` | PORT (i2c bus `STM32_I2C2`, 400 kHz). |
| `SC_INT_N` | PORT — the single SC interrupt (wire-OR). |
| `PMON_ALERT_N`, `USBOTG_FLT_N`, `PD_FLT_N` | PORT — telemetry flags into the expander. |
| `PL_BTN0/1`, `STM32_NRST`, `PUDC_34` | PORT — buttons + config strap. |

## Pull-ups / straps this sheet OWNS

| net | pull | rail |
|-----|------|------|
| `STM32_I2C2_SCL`, `STM32_I2C2_SDA` | 4k7 | `+3V3_SC` |
| `SC_INT_N` (U1.INT#) | 10k | `+3V3_SC` |
| `BU_OVR_LCD_BL` (P10) | 100k pull**down** | GND |
| `BU_P16` / `BU_P17` (P16/P17 spare) | 100k | GND |
| `PL_BTN0`, `PL_BTN1` | 10k | `+3V3` |
| `PUDC_34` | 10k | GND |

LCSC: 100k C25803, 10k C25804, 4k7 C23162, 100n C14663.

## Local test vs board gates

`test_bringup_rails.py` runs offline: model completeness (with `SW6.4`/`SW6.6`
NC), rail/port classes, the design_rules slice (I2C pull-up present, NRST RC
present, no floating strap), part/spice slices, and the surface invariants this
sheet owns (3 DIPs, the TCA9535 @0x20, the 4k7 I2C pulls, the single 10k INT
pull-up, the P10/P16/P17 don't-float pulldowns, the 10k button pulls, the PUDC
10k-to-GND strap, the SC-rail/I2C testpoints). The cross-board control-graph
(which EN cell each port feeds) stays at board level (`schgen board`).

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/bringup_rails/test_bringup_rails.py -q
```
