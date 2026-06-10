# bringup_power_gating — staged bring-up architecture (wave-2 research dossier)

Researched 2026-06-10 against PLAN.md locked decisions: USB-C PD 20V-only input, carrier
rails +5V / +3V3 / +1V8, DIP + STM32-override bring-up, 4-layer JLC7628, prefer JLC Basic.
Every part below was live-verified on LCSC/JLCPCB on 2026-06-10 (stock + Basic/Extended as
seen that day). All stock figures are JLCPCB assembly-stock numbers unless noted.

---

## 1. Architecture summary

Three bring-up stages (PLAN): (1) rails on, rail-by-rail, switches only; (2) user LEDs;
(3) every module individually power-gated. One uniform **EN cell** implements
"DIP switch AND STM32 override" for every enable in the system:

```
+3V3_SC                          +3V3_SC
   |                                |
  [DIP pos n]                     [100k pullup]          SN74LVC1G08 (VCC=+3V3_SC)
   |________ A ____________________ |                    .----------.
             |                      +------ B ---------->|A      Y  |---> EN_<thing>
           [100k pulldown]          |                    |B         |
             |                 STM32 GPIO / TCA9535 P0x  '----------'
            GND                (Hi-Z at reset => B=1)
```

- **Logic domain = +3V3_SC** (J3 pin 37). This rail is generated ON the SoM from VIN
  (SoM Power sheet: MPM3822 buck) and is alive as soon as Type-C hands over the default
  5 V VBUS — i.e. *before* PD negotiation and before any carrier rail. Verified in
  `boards/som/schematic/Power.kicad_sch` + `carrier/som_interface.json` (J3.37).
- **AND, not OR.** Chosen semantics: DIP is the master, STM32 is a *veto* (force-OFF).
  - STM32 unprogrammed / GPIO Hi-Z / TCA9535 unconfigured (its POR state is all-inputs)
    → 100k pull-up makes B=1 → pure switch control. Stage-1 "switches only" works with
    a blank system controller.
  - Software can kill any rail/module (drive B low) for scripted sequencing, brown-out
    experiments, or fault isolation.
  - Deliberately NOT possible: software force-ON while the DIP is off — that is the
    safe direction for a bring-up board (a probe-shorted module stays dead until a
    human flips the switch).
  - Diode-OR / discrete alternatives were evaluated and rejected: a diode-OR gives
    force-ON (wrong direction), loses ~0.3–0.6 V of EN headroom, and leaves EN floating
    when both sources idle. A clean 1-gate AND is $0.049 — there is no reason to be
    clever. 74LVC1G32 (OR) verified as stocked (C10096) in case a force-ON line is ever
    wanted; not used.
- **Gate**: SN74LVC1G08DBVR, SOT-23-5, pinout **1=A, 2=B, 3=GND, 4=Y, 5=VCC**,
  VCC = +3V3_SC, 100 nF decoupling each. Inputs are 5.5 V tolerant; output is 3.3 V
  CMOS, rail-to-rail, 32 mA drive — drives any regulator/load-switch EN directly.
- 11 EN cells: 3 rails + 8 module switches (one DSHP04 + one DSHP08 = 12 DIP positions,
  1 spare position wired to a spare gate footprint = EN_LCD_BL provision).

### STM32 override fan-out (8 GPIOs is not enough)
J3 exposes exactly STM32_GPIO1..8 (+ DAC1/2, NRST, BOOT0) — 12 enables don't fit.
Split:
- **Rails (3) = direct GPIOs** (robust even if I2C is down):
  STM32_GPIO1 → override +5V, STM32_GPIO2 → +3V3, STM32_GPIO3 → +1V8.
- **Modules (8) = TCA9535PWR 16-bit I2C expander** on the same STM32 I2C bus already
  used by usb_pd's FUSB302 (ports `STM32_I2C2_SDA` / `STM32_I2C2_SCL`).
  - VCC = +3V3_SC, 100 nF. I2C address pins A0=A1=A2=GND → **0x20** (FUSB302B is 0x22 —
    no clash, same bus).
  - TSSOP-24 pinout (TI SCPS201E): 1=INT#, 2=A1, 3=A2, 4..11=P00..P07, 12=GND,
    13..20=P10..P17, 21=A0, 22=SCL, 23=SDA, 24=VCC.
  - **POR state: all 16 ports are inputs** (datasheet §3) → with the cell's 100k
    pull-ups, everything defaults to DIP control. Exactly the contract we need.
  - INT# is open-drain: 10k pull-up to +3V3_SC, route to **STM32_GPIO4** (optional
    readback interrupt; can be left for firmware to ignore).
  - TCA9535 has **no internal I/O pull-ups** (unlike PCA9555): unused P10..P17 must
    not float → 100k to GND on each (8× C25803). P00..P07 are held by the cell pull-ups.
  - SDA/SCL bus pull-ups: 4.7k — but see Risk R1 (they must live on +3V3_SC, not +3V3).
- GPIO budget after this subsystem: GPIO1-3 rails, GPIO4 expander INT, +2 consumed as
  I2C2 (SDA/SCL ride on two of the eight — see Risk R2), GPIO usage by usb_pd's
  STM32_FUSB302_INT — effectively ~0–1 spare. The expander's 8 spare lines (P10..P17)
  are the expansion path, not more J3 GPIOs.

---

## 2. Chosen parts (all live-verified 2026-06-10)

| Role | MPN | LCSC | Stock seen | Basic/Ext | Unit $ (qty1) |
|---|---|---|---|---|---|
| Module load switch (×8) | SY6280AAC (Silergy) | C55136 | 111,264 | Extended | 0.0955 |
| EN AND gate (×11+1 spare) | SN74LVC1G08DBVR (TI) | C7666 | 259,342 | Extended | 0.0493 |
| STM32 override expander | TCA9535PWR (TI) | C130204 | 12,846 | Extended | 1.0781 |
| Rail DIP (4-pos, 1.27 mm SMD) | DSHP04TSGER (Kangshen) | C3293144 | 33,538 | Extended | 0.5165 |
| Module DIP (8-pos, 1.27 mm SMD) | DSHP08TSGER (Kangshen) | C3293147 | 37,706 | Extended | 0.5857 |
| Buttons (reset + 2 user) | TS-1187A-B-A-B (XKB) | C318884 | 1,830,400 | **Basic** | 0.0203 |
| PG / module status LEDs (red) | KT-0603R (KENTO) | C2286 | 6,237,246 | **Basic** | 0.0070 |
| User LEDs ×4 (yellow, distinct) | LTST-C190KFKT (Lite-On) | C157740 | 38,848 (LCSC list) | Extended | ~0.03 |
| +1V8 PG sense FET | AO3400A (AOS) | C20917 | 1,862,683 | **Basic** | 0.0837 |
| R 100k (pull-up/-down) | 0603WAF1003T5E | C25803 | 9,658,890 | **Basic** | 0.0018 |
| R 10k (INT pull-up, NRST, btn) | 0603WAF1002T5E | C25804 | 3,983,160 | **Basic** | 0.0100 |
| R 4.7k (I2C pull-ups) | 0603WAF4701T5E | C23162 | 9,126,951 | **Basic** | ~0.002 |
| R 1k (5 V LED series) | 0603WAF1001T5E | C21190 | 13,045,436 | **Basic** | 0.0016 |
| R 330 (3V3 LED series) | 0603WAF3300T5E | C23138 | 3,787,863 | **Basic** | ~0.002 |
| R 6.8k (ILIM = 1.0 A) | 0603WAF6801T5E | C23212 | 606,758 | **Basic** | 0.0017 |
| R 13k (ILIM = 523 mA) | 0603WAF1302T5E | C22797 | 380,477 | **Basic** | ~0.002 |
| C 100n 0603 (decoupling) | CL10B104KB8NNNC (Samsung) | C1591 | 45,893,814 | **Basic** | ~0.001 |

Extended-feeder count for the whole subsystem: 7 (SY6280, 1G08, TCA9535, DSHP04,
DSHP08, LTST-C190KFKT, +0 spare) — acceptable per PLAN ("Extended where design
quality demands"). Everything else rides Basic feeders.

### Load-switch family shoot-out (why SY6280AAC)

| | **SY6280AAC C55136** | TPS22918DBVR C131941 | AP22802AW5/BW5 C211404/C445532 |
|---|---|---|---|
| Stock / status | 111,264 / Ext | 32,184 / Ext | **780 / 2,685** — disqualifying |
| VIN range | 2.4–5.5 V | 1.1–5.5 V | 2.5–5.5 V |
| Current | 2 A max, **programmable limit** ILIM = 6800/RSET | 2 A, **no current limit** (inrush slew only via CT) | 2 A, fixed ~3 A short-circuit limit |
| RON | 80 mΩ | 53 mΩ | 70 mΩ |
| EN | Active-high, must not float | Active-high | AW5 active-high / BW5 active-low |
| Soft-start | Built-in soft turn-on | CT-pin adjustable | Fixed slew |
| Output discharge | No | Yes (QOD pin) | Yes |
| Protection | OCP (constant-current foldback), OTP, reverse blocking | none beyond thermal | OCP/OTP/UVLO |
| Price | **$0.10** | $0.25 | — |

**Pick: SY6280AAC for every module gate.** On a bring-up board the per-module
*programmable current limit* is the killer feature — a shorted module folds back at its
own limit instead of dragging down +3V3 for everything else; the status LED on that one
output sags and tells you where the fault is. TPS22918's QOD is nice-to-have, not
need-to-have (module rails decay through their loads); it stays the documented alternate
(drop-in concept, SOT-23-6, EN active-high) if Silergy stock ever dries up.

SY6280AAC pinout (SOT-23-5, Silergy DS): **1=OUT, 2=GND, 3=ISET, 4=EN, 5=IN.**
ILIM(A) = 6800 / RSET(Ω): 13 kΩ → 523 mA, 6.8 kΩ → 1.0 A, 2×6.8 kΩ parallel → 2.0 A
(stay on the verified Basic value rather than introducing 3.3 kΩ).

---

## 3. Reference circuit (pin-level, sufficient to author the schgen .py)

### 3.1 Rail-enable cells (×3)
Per rail R ∈ {5V0, 3V3, 1V8}: U_AND (SN74LVC1G08DBVR)
- pin 5 VCC → `+3V3_SC`, 100 nF (C1591) to GND
- pin 1 A → net `BU_DIP_<R>`: DIP SW1 position (n) — one side `+3V3_SC`, other side this
  net + 100k (C25803) to GND. Closed = enabled.
- pin 2 B → net `BU_OVR_<R>`: 100k (C25803) to `+3V3_SC`, + port `STM32_RAIL_EN_<R>`
  (J3 binding: STM32_GPIO1/2/3).
- pin 3 GND; pin 4 Y → **port `EN_5V0` / `EN_3V3` / `EN_1V8`** (consumed by the power
  subsystem's regulator EN pins).
- Interface contract for the power subsystem: EN nets are 3.3 V CMOS, active-high,
  push-pull, driven from the +3V3_SC domain (valid whenever VIN present). The chosen
  bucks' EN pins must (a) tolerate ≥3.3 V, (b) have VIH(EN) ≤ 2.4 V, (c) not be relied
  on with internal auto-start pull-ups — EN is always actively driven here. Virtually
  every 20 V-class buck (TPS54331/TPS56x/MP2315/SY81xx class) satisfies this; the power
  dossier must double-check its picks.
- Bring-up order is inherently 5V → 3V3 (+3V3 buck is fed from +5V per PLAN) → 1V8.
  A closed 3V3 DIP with 5V off simply does nothing — benign.

### 3.2 Module load-switch cells (×8, SY6280AAC + AND cell each)
DIP SW2 (DSHP08TSGER) position / TCA9535 port / switch:

| # | Module | SY6280 IN | OUT net (port) | RSET (ISET→GND) | Limit |
|---|---|---|---|---|---|
| 1 | HDMI TX | +3V3 | `+3V3_HDMI_TX` | 13k C22797 | 523 mA |
| 2 | HDMI RX | +3V3 | `+3V3_HDMI_RX` | 13k | 523 mA |
| 3 | LCD logic+touch | +3V3 | `+3V3_LCD` | 6.8k C23212 | 1.0 A |
| 4 | Camera | +3V3 | `+3V3_CAM` | 13k | 523 mA |
| 5 | microSD (+TXS02612) | +3V3 | `+3V3_SD` | 6.8k | 1.0 A |
| 6 | USB OTG VBUS | **+5V** | `+5V_USB` | 6.8k | 1.0 A |
| 7 | PMOD | +3V3 | `+3V3_PMOD` | 13k | 523 mA |
| 8 | User LEDs (stage 2) | +3V3 | `+3V3_USER_LED` | 13k | 523 mA |

Wiring per switch: pin 5 IN ← source rail (+ 100 nF local), pin 1 OUT → gated net
(+ 100 nF local; each module subsystem owns its own bulk), pin 2 GND, pin 3 ISET →
RSET → GND, pin 4 EN ← Y of its AND cell (`BU_DIP_<mod>` from SW2 pos n,
`BU_OVR_<mod>` from TCA9535 P0(n-1), both with the standard 100k pull network).
EN must never float — it never does (gate is push-pull).
Note: stage-2 "user LED enable" is implemented as module-switch #8 + DIP **SW1 pos 4**
(the 4-position rail DIP's spare), keeping SW2's eight positions for real modules.
SW2 has no spare; the EN_LCD_BL provision (gated 5 V backlight-boost enable, owned by
lvds_lcd_power) uses TCA9535 P10 + a DNP gate/footprint if wanted later.

### 3.3 Per-rail PG LEDs (3)
- `+5V`: KT-0603R + 1k (C21190) in series to GND → ~3 mA.
- `+3V3`: KT-0603R + 330R (C23138) to GND → ~3.9 mA.
- `+1V8`: red LED Vf (~2.0 V) exceeds the rail — sense it instead:
  AO3400A (SOT-23: 1=G, 2=S, 3=D): G ← `+1V8` via 10k (C25804) with 100k G→GND;
  S → GND; D → 330R → KT-0603R → `+3V3_SC`. Vgs(th) ≤ 1.45 V max < 1.8 V → lights
  whenever the rail is genuinely up. (Alternate: regulator PG pin via same FET — power
  dossier's call if its 1V8 part has PG.)
- Per-module status LEDs (8): KT-0603R + 330R on each SY6280 OUT (1k on the +5V_USB
  output). Total red LEDs: 11.

### 3.4 User LEDs (4× PL) and buttons (2× user + reset)
- LEDs: LTST-C190KFKT (yellow, Vf≈2.0 V — visually distinct from the red
  infrastructure LEDs). Anodes bused on `+3V3_USER_LED` (switch #8); cathode → 330R →
  PL pin. **Active-LOW at the pin** (PL drives 0 to light); ~3.9 mA per LED, well
  inside a 3.3 V LVCMOS bank pin.
- User buttons: TS-1187A-B-A-B to GND, 10k (C25804) pull-up to `+3V3` (must match the
  bank VCCO of the chosen pins), 100 nF (C1591) across the switch for debounce.
  Active-LOW.
- Reset button: TS-1187A-B-A-B from `STM32_NRST` (J3.47) to GND + 100 nF to GND at the
  button. STM32 NRST has the internal ~40k pull-up; no external pull-up required.
  (This resets the system controller, which owns Zynq power/reset supervision on the
  SoM — there is no direct PS_POR pin on J1–J3.)
- TS-1187A-B-A-B is SMD-4P (5.1×5.1 mm): pins are two internally-bridged pairs —
  treat 1/2 as one contact and 3/4 as the other in the symbol.

**PL pin budget note:** 6 single-ended, slow PL pins total (4 LED + 2 BTN). Take them
from bank 33 leftovers on J1 (3.3 V VCCO bank, plain `IO_*_33` pins, e.g. IO_25_33-class
non-clock pins). J1+J2 expose ~170 PL I/Os; after LCD RGB888 (~30), camera, PMOD (8) and
FMC LA claims, 6 unconstrained singles are trivially available. Final pin assignment is
the P3 linker's job — this subsystem only publishes the ports.

### 3.5 TCA9535 hookup (recap, TSSOP-24)
24 VCC=+3V3_SC (100 nF); 12 GND; 21/2/3 A0/A1/A2=GND (addr 0x20); 22 SCL / 23 SDA =
`STM32_I2C2_SCL`/`STM32_I2C2_SDA` with 4.7k (C23162) pull-ups **to +3V3_SC**;
1 INT# → 10k to +3V3_SC + port `STM32_BRINGUP_INT` (J3: STM32_GPIO4);
4–11 P00..P07 → the eight `BU_OVR_<mod>` nets; 13–20 P10..P17 each 100k to GND (no
internal pulls in this device; P10 doubles as the EN_LCD_BL provision driver).

---

## 4. PORT list (names consistent with som_interface.json + wave-1 subsystems)

Consumed rails: `+3V3_SC` (J3.37), `+5V`, `+3V3`, `+1V8` (sense only), `GND`.

| Port | Dir | Binds to | Notes |
|---|---|---|---|
| `STM32_RAIL_EN_5V0` | in | J3 STM32_GPIO1 | 100k PU to +3V3_SC; veto for +5V |
| `STM32_RAIL_EN_3V3` | in | J3 STM32_GPIO2 | idem +3V3 |
| `STM32_RAIL_EN_1V8` | in | J3 STM32_GPIO3 | idem +1V8 |
| `STM32_I2C2_SDA` / `STM32_I2C2_SCL` | bidir | shared bus w/ usb_pd FUSB302 | TCA9535 @0x20 |
| `STM32_BRINGUP_INT` | out (OD) | J3 STM32_GPIO4 | optional expander IRQ |
| `EN_5V0`, `EN_3V3`, `EN_1V8` | out | power subsystem regulator ENs | 3.3 V CMOS, active-high |
| `+3V3_HDMI_TX`, `+3V3_HDMI_RX`, `+3V3_LCD`, `+3V3_CAM`, `+3V3_SD`, `+3V3_PMOD`, `+3V3_USER_LED` | out (rail) | module subsystems | gated, current-limited |
| `+5V_USB` | out (rail) | usbc_otg VBUS source | 1.0 A limited |
| `EN_LCD_BL` | out (provision) | lvds_lcd_power boost EN | TCA9535 P10 / DNP gate |
| `PL_LED0..PL_LED3` | in (sink) | J1 bank-33 PL pins | active-LOW drive |
| `PL_BTN0`, `PL_BTN1` | out | J1 bank-33 PL pins | active-LOW, RC-debounced |
| `STM32_NRST` | bidir | J3.47 | reset button hangs here |

DIP map (silkscreen contract): **SW1** (DSHP04TSGER) 1=+5V, 2=+3V3, 3=+1V8, 4=USER_LED.
**SW2** (DSHP08TSGER) 1=HDMI_TX, 2=HDMI_RX, 3=LCD, 4=CAM, 5=SD, 6=USB, 7=PMOD, 8=spare.
DIP contacts are rated 24 V / 25 mA — they only ever carry a 100k pull current here.

---

## 5. Risks / cross-subsystem flags / alternates

- **R1 (flag for usb_pd, important):** usb_pd currently powers FUSB302 VDD and the
  I2C/INT pull-ups from `+3V3` — a DIP-gated carrier rail. PD negotiation must happen
  *before* any carrier rail is enabled (board boots on 5 V default VBUS). FUSB302 VDD
  and the shared-bus pull-ups must move to `+3V3_SC`, or 20 V never arrives with the
  DIPs off. This dossier already places the bus pull-ups on +3V3_SC.
- **R2 (J3 I2C binding):** J3 carries no dedicated I2C nets — `STM32_I2C2_SDA/SCL` must
  map onto two of STM32_GPIO1..8 whose STM32G431CBU pins carry an I2C AF (e.g.
  PA8/PA9 = I2C2). Verify the GPIOn↔MCU-pin map when authoring the J3 sheet; if no
  I2C-capable pair lands on J3, fall back to firmware bit-bang (FUSB302 + TCA9535 both
  tolerate it; 400 kHz not required).
- **R3 (+3V3_SC budget):** subsystem draw on +3V3_SC is <5 mA (gates µA, TCA9535 µA,
  pull networks, 2 LEDs ~8 mA worst). SoM's MPM3822 (2 A) has headroom; flag the number
  to the power dossier for the rail budget table anyway.
- **R4 (green-on-3V3 trap):** emerald-green 0603 LEDs (KT-0603G C12624, Vf≈3.1 V) are
  marginal on a 3.3 V rail — that is why every rail/status indicator is red (Vf≈2.0 V)
  and the user LEDs are yellow. Do not "upgrade" PG LEDs to green InGaN parts.
- **R5 (no output discharge):** SY6280 lacks QOD; a toggled-off module rail decays
  through its load. If a module ever needs guaranteed fast discharge for re-init
  (SD card power-cycle is the realistic case), either add 10k bleed on `+3V3_SD` or
  swap that one position to TPS22918DBVR C131941 (verified above) with its QOD pin
  tied to OUT.
- **R6 (never on VIN):** SY6280/LVC parts are 5.5 V max — nothing in this subsystem
  touches VIN(20 V). The +5V rail switch-on transient is the regulator's soft-start
  problem, not ours.
- **R7 (1V8 PG threshold):** AO3400A Vgs(th) spread tops at 1.45 V; at 1.8 V the LED
  current (~4 mA) is comfortably available, but the LED is an indicator, not a
  measurement. If the 1V8 regulator pick has a PG pin, prefer it (same FET stage).
- **Alternates (verified stock 2026-06-10):** load switch TPS22918DBVR C131941
  (32,184, Ext, $0.25); expander XL9535 C561273 (14,352, TSSOP-24, cheap clone) or
  PCA9555PW,118 C128392 (3,027 — thin); OR-gate option SN74LVC1G32DBVR C10096
  (120,263, Ext, $0.073); green LED KT-0603G C12624 (34,631, Ext) for non-3V3 uses;
  AP22802 rejected outright on stock (C211404: 780; C445532: 2,685).
- **BOM/feeder cost:** ~11 gates + 8 switches + expander + 2 DIPs + 3 buttons +
  15 LEDs + ~45 passives ≈ **$4.1** of components and 7 Extended feeders ($21 in
  one-off feeder fees at JLC's $3/feeder) per board-spin — negligible against the
  debugging time a stuck non-gated board burns.

Datasheet anchors: Silergy SY6280 (ILIM = 6800/RSET, pinout) —
https://datasheet.lcsc.com/lcsc/Silergy-Corp-SY6280AAAC_C207620.pdf ;
TI TCA9535 SCPS201E (pinout, POR-inputs, OD INT, no internal pulls) —
https://www.ti.com/lit/ds/symlink/tca9535.pdf ; TI TPS22918, Diodes AP22802 (enable
polarity variants) per manufacturer datasheets.
