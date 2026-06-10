# lcd_backlight — 40-pin TTL RGB888 LCD + backlight boost + capacitive touch

Wave-2 research dossier (2026-06-10). Scope: the carrier's generic LCD port per PLAN.md
locked decisions — "LCD: generic 40-pin TTL RGB888 FFC (0.5mm) + touch I2C + on-carrier
backlight boost". Rails available: +5V, +3V3 (+ module-gated variants per the bring-up
architecture). 4-layer JLC7628; TTL parallel video is NOT impedance-controlled (no diff
pairs); prefer JLC Basic parts.

All LCSC stock numbers below were checked live on 2026-06-10 (LCSC product pages and the
JLCPCB in-stock parts index).

---

## 1. The de-facto 40-pin TTL RGB888 pinout

The "AT070TN90-class" 7" 800x480 panels with a 50-pin tail exist (AT070TN90/92/94 are
50-pin), but the **dominant 40-pin 0.5mm convention** for the 4.3"–7" 480x272/800x480
class (Innolux AT043TN24 V.7 lineage; used identically by the HAOYU HY7-LCD /
HY070CTP-A 7" 800x480 modules, Adafruit #2353, and the SSD1963/RA8875 ecosystem boards)
is:

| Pin | Symbol | Function |
|-----|--------|----------|
| 1 | VLED- | Backlight LED string cathode (current-sense return) |
| 2 | VLED+ | Backlight LED string anode (boost output) |
| 3 | GND | Ground |
| 4 | VDD | Panel logic supply, 3.3V (typ 25–75mA) |
| 5–12 | R0–R7 | Red data, LSB→MSB |
| 13–20 | G0–G7 | Green data, LSB→MSB |
| 21–28 | B0–B7 | Blue data, LSB→MSB |
| 29 | GND | Ground |
| 30 | PCLK (DCLK) | Pixel clock (≈33.3MHz typ for 800x480@60) |
| 31 | DISP | Display on/off (high = on) |
| 32 | HSYNC | Horizontal sync |
| 33 | VSYNC | Vertical sync |
| 34 | DE | Data enable |
| 35 | NC | (MODE on some panels — DE/SYNC select; NC on most) |
| 36 | GND | Ground |
| 37 | X1 / **CTP-SDA** | Resistive XR — or capacitive-touch I2C SDA |
| 38 | Y1 / **CTP-SCL** | Resistive YD — or capacitive-touch I2C SCL |
| 39 | X2 / **CTP-RST** | Resistive XL — or capacitive-touch reset |
| 40 | Y2 / **CTP-INT** | Resistive YU — or capacitive-touch interrupt |

Key facts verified:
- HAOYU HY7-LCD (7" 800x480, "Standard 40 PIN") documents exactly pins 1–40 as above
  with 4-wire resistive touch on 37–40.
- HAOYU HY070CTP-A (same panel + capacitive touch) re-uses 37/38/39/40 as
  CTP-SDA / CTP-SCL / CTP-RST / CTP-INT (FocalTech FT5206 on-panel; GT911-class
  modules wire the same four signals). The carrier therefore gets capacitive touch
  **through the same 40-pin connector** — no extra tail needed for this class.
- Adafruit #2353 (same 7" class): backlight needs a **constant-current boost,
  125–150mA, compliance up to ~9V** (3-series LED strings, ≈9.6V worst case).
- 800x480@60Hz: PCLK ≈ 33.3MHz (1056×525 total, ILI6122-class column drivers);
  panels accept ~26–47MHz.

Carrier decision: wire 37–40 as the capacitive-touch I2C group (3.3V). Resistive
panels are NOT supported natively (no ADC on those nets) — see risks.

---

## 2. Chosen parts (all verified on LCSC 2026-06-10)

| # | Part | MPN | LCSC | Stock seen | Basic/Ext | Unit price (qty 5+) |
|---|------|-----|------|-----------|-----------|---------------------|
| J_LCD | FFC/FPC 40P 0.5mm, **bottom contact**, R/A SMD, flip/slide lock | JUSHUO (XUNPU) AFC07-S40FCA-00 | **C262572** | 9,940 | Extended | $0.223 |
| J_LCD alt | FFC/FPC 40P 0.5mm, **top contact** (same family) | JUSHUO AFC07-S40ECA-00 | **C262648** | 46,835 | Extended | $0.215 |
| J_TP (optional) | FFC/FPC 6P 0.5mm, bottom contact (separate CTP tails) | JUSHUO AFC07-S06FCA-00 | **C262553** | 19,276 | Extended | ~$0.096 |
| U_BL | Boost WLED driver, 30V/2A/1MHz, SOT-23-6 | Silergy SY7201ABC | **C82173** | 15,175 | Extended | $0.309 |
| L_BL | 10µH power inductor 4x4mm (Isat ≈ 1.1A) | Sunlord SWPA4030S100MT | **C38117** | 34,446 | Extended | $0.062 |
| D_BL | Schottky 40V/3A SMA | MDD SS34 | **C8678** | 3,282,802 | **Basic** | $0.026 |
| C_BL_OUT | 1µF 50V X7R 0805 (rated above 30V OVP clamp) | Samsung CL21B105KBFNNNE | **C28323** | 5,331,021 | **Basic** | $0.008 |
| C_BL_IN | 10µF 25V X5R 0805 | Samsung CL21A106KAYNNNE | **C15850** | 12,668,317 | **Basic** | $0.009 |
| R_ISET | 1.5Ω 1% 0603 (I_LED = 0.2V/R = 133mA) | UNI-ROYAL 0603WAF150KT5E | **C22769** | 42,227 | Extended | <$0.01 |
| R_SER ×4(+) | 22Ω 1% 0603 series terminations | UNI-ROYAL 0603WAF220JT5E | **C23345** | 5,310,666 | **Basic** | <$0.01 |
| R_PU ×2 | 4.7kΩ 1% 0603 (touch I2C pull-ups) | UNI-ROYAL 0603WAF4701T5E | **C23162** | 9,126,951 | **Basic** | <$0.01 |
| R_PU/PD | 10kΩ 1% 0603 (DISP pull-up) | UNI-ROYAL 0603WAF1002T5E | **C25804** | 37,165,617 | **Basic** | <$0.01 |
| R_PD ×2 | 100kΩ 1% 0603 (BL_PWM + CTP_RST pull-downs) | UNI-ROYAL 0603WAF1003T5E | **C25803** | 14,797,688 | **Basic** | <$0.01 |
| C_VDD | 100nF 50V X7R 0603 (panel VDD decoupling, project standard) | Samsung CL10B104KB8NNNC | **C1591** | 45,893,814 | see note | <$0.01 |

Notes:
- AFC07 naming decode (confirmed from LCSC titles): `S40` = 40 positions, `E`=top
  contact / `F`=bottom contact, trailing `A`/`C` = packaging. Pick E vs F per the
  panel-tail fold direction in the mechanical design (both footprint-compatible
  pad rows, contacts mirrored). Bottom-contact (FCA) is the common choice for
  panel-behind-board mounting; the top-contact ECA has 4.7× the stock if mechanics
  allow.
- C1591 is the classic high-runner 100n; the JLC index showed its basic flag
  off on 2026-06-10 (historically Basic). Preflight (P2) will resolve; any 100n
  0603 Basic substitutes.
- No 0.5mm 40P FFC connector exists in the JLC **Basic** library — Extended is
  unavoidable here ("Extended where design quality demands", PLAN.md).
- PT4103 (the other obvious backlight driver) is **not in the JLC parts library
  at all** — search returned zero components. SY7201ABC is the stocked choice.

---

## 3. Reference circuit (pin-level, sufficient to author the schgen subsystem)

### 3.1 J_LCD — 40P 0.5mm FFC (C262572)

- Pin 1 `VLED-` → net `LCD_VLED_K` → SY7201 FB node (see 3.2).
- Pin 2 `VLED+` → net `LCD_VLED_A` = boost output node.
- Pins 3, 29, 36 → `GND`.
- Pin 4 `VDD` → `+3V3_LCD` (module-gated rail from the bringup subsystem, per
  PLAN.md "module rails become gated nets"). Decouple at the pin: 10µF (C15850)
  + 100n (C1591).
- Pins 5–12 → nets `LCD_R0`..`LCD_R7`; pins 13–20 → `LCD_G0`..`LCD_G7`;
  pins 21–28 → `LCD_B0`..`LCD_B7`. Optional but recommended: 22Ω series
  (C23345) in each line, resistor at the SoM side of the trace (24 pcs).
  Minimum viable: direct connection (TTL inputs, FFC run is short).
- Pin 30 `PCLK` ← port `LCD_PCLK` through **mandatory** 22Ω series (C23345).
- Pin 31 `DISP` ← port `LCD_DISP`; 10k pull-up (C25804) to `+3V3_LCD` so the
  panel defaults ON when the rail is gated on and the PL is unconfigured.
- Pin 32 `HSYNC` ← `LCD_HSYNC`, pin 33 `VSYNC` ← `LCD_VSYNC`, pin 34 `DE` ←
  `LCD_DE` — each through 22Ω series (recommended).
- Pin 35 `NC` — explicit author no-connect.
- Pin 37 `CTP-SDA` → net `LCD_CTP_SDA`, 4.7k pull-up (C23162) to `+3V3_LCD`.
- Pin 38 `CTP-SCL` → net `LCD_CTP_SCL`, 4.7k pull-up (C23162) to `+3V3_LCD`.
- Pin 39 `CTP-RST` → net `LCD_CTP_RST`, 100k pull-down (C25803) — touch held in
  reset until the PL drives it high (safe default).
- Pin 40 `CTP-INT` → net `LCD_CTP_INT`, **no pull** — GT911-class controllers
  sample INT during reset release to select the I2C address (low → 0x5D,
  high → 0x14); the host drives it momentarily then releases to input.
  FT5206-class (0x38) treats it as a plain output. Both work with this wiring.

### 3.2 Backlight boost — SY7201ABC (C82173), datasheet rev 0.4 verified

SY7201 SOT-23-6 pinout: 1 `LX`, 2 `GND`, 3 `FB`, 4 `EN/PWM`, 5 `OVP`, 6 `IN`.
Electricals: VIN 2.5–30V, VREF(FB) = 200mV ±2%, switch limit 2A, 1MHz fixed,
open-LED clamp (OVP pin) typ 30V, internal soft-start, EN thresholds 1.5V/0.4V
(abs max 4V — 3.3V logic direct), PWM dimming ≥ 20kHz.

Wiring:
- `IN` (6) ← `+5V_LCD` (gated 5V module rail). Decouple: 10µF (C15850) + the
  datasheet's 1µF (use C28323) at the pin.
- `L1` 10µH (C38117) from `+5V_LCD` to `LX` (1).
- `D1` SS34 (C8678): anode → `LX`, cathode → `LCD_VLED_A` (J_LCD pin 2).
- `C_OUT` 1µF 50V (C28323) from `LCD_VLED_A` to GND — 50V rating survives the
  30V open-LED clamp.
- `OVP` (5) → `LCD_VLED_A` (output-sense per datasheet application circuit).
- `FB` (3) → `LCD_VLED_K` (J_LCD pin 1) and `R_ISET` 1.5Ω (C22769) from FB to
  GND. **I_LED = 0.2V / R_ISET = 133mA** — inside the 125–150mA window for the
  7" 800x480 class (≈9.6V string). Dissipation in R_ISET: 27mW (0603 fine).
- `EN/PWM` (4) ← port `LCD_BL_PWM`; 100k pull-down (C25803) → backlight OFF by
  default. Drive high for 100%, or PWM at ≥ 20kHz for dimming.
- `GND` (2) → GND.

Operating point check (5V in → 9.6V/133mA out): D ≈ 0.52, Iin ≈ 0.30A,
inductor ripple at 1MHz/10µH ≈ 0.26A p-p → peak ≈ 0.43A. Margins: 2A switch
limit (4.6×), 1.1A Isat (2.5×). Headroom exists for panels up to ~27V strings
by changing R_ISET only (I = 0.2V/R).

### 3.3 Optional separate touch tail — J_TP 6P 0.5mm (C262553)

For CTP glass sold with its own 6-pin tail (instead of touch-on-40-pin). Wire
in parallel with the same nets: GND, `+3V3_LCD` (+100n local), `LCD_CTP_SCL`,
`LCD_CTP_SDA`, `LCD_CTP_INT`, `LCD_CTP_RST`. **Pin ORDER on 6-pin CTP tails is
vendor-specific** (no de-facto standard was verifiable) — fix the order when the
actual touch glass is chosen; stuff-option DNP by default. The four signals and
levels (3.3V) are universal for GT911/FT5206-class controllers.

### 3.4 Power gating (interface to the bringup subsystem)

This subsystem CONSUMES `+5V_LCD` and `+3V3_LCD`; the load switches + enable
DIP/STM32-override + status LEDs live in the wave-2 `bringup` subsystem
(TPS22918/SY6280-class) per PLAN.md. Budget to declare to bringup:
- `+3V3_LCD`: ≤ 100mA (panel logic 25–75mA + touch ≤ 25mA).
- `+5V_LCD`: ≤ 0.45A (boost input at 133mA LED current, plus margin).

---

## 4. PORT list (schgen subsystem `lcd`)

Naming follows existing subsystem style (functional SCREAMING_SNAKE, cf.
`USB_UART_DP`, `STM32_I2C2_SDA` in carrier/subsystems/). All LCD signals are
PL-side and will be linked to J2 bank-13 IOs (`IO_*_13` in som_interface.json);
none collide with existing port names (checked against usb_pd, uart_bridge,
ethernet).

| Port | Dir (SoM side) | Count | Notes |
|------|----------------|-------|-------|
| `LCD_R0`..`LCD_R7` | out | 8 | red data |
| `LCD_G0`..`LCD_G7` | out | 8 | green data |
| `LCD_B0`..`LCD_B7` | out | 8 | blue data |
| `LCD_PCLK` | out | 1 | ≈33.3MHz, 22Ω series |
| `LCD_HSYNC` | out | 1 | |
| `LCD_VSYNC` | out | 1 | |
| `LCD_DE` | out | 1 | |
| `LCD_DISP` | out | 1 | 10k pull-up → default on |
| `LCD_BL_PWM` | out | 1 | SY7201 EN/PWM, 100k pull-down → default off |
| `LCD_CTP_SDA` | bidir | 1 | 4.7k to +3V3_LCD |
| `LCD_CTP_SCL` | out (od) | 1 | 4.7k to +3V3_LCD |
| `LCD_CTP_INT` | bidir | 1 | no pull (GT911 addr select) |
| `LCD_CTP_RST` | out | 1 | 100k pull-down |
| `+5V_LCD`, `+3V3_LCD`, `GND` | rails | — | gated rails from bringup |

Total PL pins: **28 mandatory** (24 RGB + PCLK/HS/VS/DE) + 6 housekeeping
(DISP, BL_PWM, CTP×4) = **34 max**.

## 5. PL pin budget vs the SoM

From carrier/som_interface.json (counted): J2 carries **43 bank-13 IOs** and
29 bank-33 IOs; J3 carries banks 34/35 (+10 of 33). The whole LCD subsystem
fits **one bank: bank 13 on J2** (34 ≤ 43, 9 spare), keeping the bus on one
VCCO and one connector. Requirement: **+VCCO_13 (J2 pins 1/2/3) = +3V3** —
record this as a bank-voltage constraint for the J2 power sheet / P3 linker.
PCLK is a PL **output**, so no clock-capable-input pin constraint applies; all
signals LVCMOS33, slow/medium slew is fine at 33MHz over a short FFC. Keep the
24-bit bus within ~±25mm of PCLK; no controlled impedance needed on JLC7628.
Stitch GND at pins 3/29/36 directly to the plane.

## 6. Risks / alternates

1. **Contact orientation (top vs bottom)** — depends on which way the panel
   tail folds. Both variants verified in stock (C262572 bottom / C262648 top).
   Decide at layout/mechanical time; footprints are not interchangeable.
2. **Resistive-touch panels**: on 4-wire variants, pins 37–40 are analog
   electrodes. Our 4.7k pull-ups + CMOS pins cannot digitize them — resistive
   touch is unsupported (would need an ADS7843-class controller; out of scope).
   The I2C pull-ups present no damage risk to a resistive panel if the PL pins
   stay tri-stated.
3. **Backlight string variance**: some 7" 40-pin panels use longer strings
   (~19V @ 40mA) instead of 3S @ 125–150mA. SY7201 covers both (30V OVP);
   only R_ISET changes (0.2V/I). Verify the chosen panel's VLED spec at
   panel-selection time; 1.5Ω/133mA is correct for the HY7/Adafruit-2353 class.
4. **SY7201 single-source**: 15k stock, Extended, Silergy only. Verified
   fallback: TI TPS61041DBVR (C9846, 6,416 in stock, Extended) — but its 250mA
   switch limit cannot deliver 133mA at 9.6V from 5V (needs ≈0.43A peak);
   usable only for low-current strings (≤60mA). If SY7201 ghosts, re-research
   a 1–2A boost LED driver (SY7202/FP5209-class, unverified).
5. **OVP event**: open-FFC with backlight enabled drives VLED_A to ~30V; C_BL_OUT
   is 50V-rated and the SS34 is 40V — covered. Keep ≥0.3mm clearance on the
   VLED_A node per JLC standard rules.
6. **6P CTP tail pin order** is vendor-specific — J_TP stays DNP until glass is
   chosen (3.3).
7. **ESD**: the FFC is user-touchable. Optional later hardening: PESD3V3-class
   TVS on CTP_SDA/SCL/INT/RST and DISP/BL nets (not in BOM; pads cheap to add).
8. **C1591 basic-flag discrepancy** in the JLC index (see table note) — P2
   preflight will report definitively.

## 7. Sources

- HAOYU HY7-LCD 7" 800x480 standard-40-pin pinout: hotmcu.com/7-inch-800x480-tft-lcd-display-touch-panel-standard-40-pin-p-57.html
- HAOYU HY070CTP-A (CTP on pins 37–40, FT5206): hotmcu.com/7-inch-800x480-tft-lcd-display-with-capacitive-touch-panel-p-65.html
- Adafruit #2353 7" 40-pin 800x480 (backlight 125–150mA, up to ~9V): adafruit.com/product/2353
- SY7201 datasheet rev 0.4 (pinout, VREF 200mV, 2A, OVP 30V, I=0.2V/R1, PWM ≥20kHz): wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/1809231811_Silergy-Corp-SY7201ABC_C82173.pdf
- LCSC product pages: C262572, C262648 (AFC07 contact-side decode), C82173 (stock/price)
- JLCPCB in-stock index (stock/Basic flags): jlcsearch.tscircuit.com (C262553, C38117, C8678, C28323, C15850, C22769, C23345, C23162, C25804, C25803, C1591, C9846; PT4103 = zero hits)
- GT911 reset/address-select behavior: Goodix GT911 datasheet (I2C 0x5D/0x14 by INT level at reset release)
- AT070TN90 is 50-pin (why it is NOT the carrier convention): cdn-shop.adafruit.com/datasheets/AT070TN90.pdf
