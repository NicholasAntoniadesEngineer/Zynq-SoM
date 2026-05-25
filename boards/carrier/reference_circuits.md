# Carrier Reference Circuits

Auto-generated design-intent record. For every IC on the carrier, this document shows the manufacturer reference circuit applied: every external part required by the datasheet, pin overrides, and layout notes. The EE reviews this document before PCB tape-out to confirm the carrier design follows each IC's reference design.

## Contents

- [U1 — TLV75733PDBVR](#u1-tlv75733pdbvr)
- [U2 — TLV75725PDBVR](#u2-tlv75725pdbvr)
- [U3 — TLV75718PDBVR](#u3-tlv75718pdbvr)
- [U1 — INA226AIDGSR](#u1-ina226aidgsr)
- [U1 — FUSB302BMPX](#u1-fusb302bmpx)
- [U2 — USBLC6-4SC6](#u2-usblc6-4sc6)
- [U1 — TPS2051CDBVR](#u1-tps2051cdbvr)
- [U1 — CP2102N-A02-GQFN24R](#u1-cp2102n-a02-gqfn24r)
- [U1 — TPD12S016PWR](#u1-tpd12s016pwr)
- [U2 — 24LC256T-I/SN](#u2-24lc256t-i-sn)
- [U1 — TPD12S016PWR](#u1-tpd12s016pwr)
- [T1 — HX5008NLT](#t1-hx5008nlt)
- [SW1 — DS-04P](#sw1-ds-04p)
- [SW2 — TS-1002S-06026C](#sw2-ts-1002s-06026c)

## U1 — TLV75733PDBVR

**Block:** power  
**Datasheet:** [TLV75733PDBVR](https://www.ti.com/lit/ds/symlink/tlv757p.pdf) (Figure 18 - Typical Application, p.18, Figure 18)  
**Footprint:** Package_TO_SOT_SMD:SOT-23-5  
**Min-circuit verified:** yes  

3.3V 1A LDO (VCCO bank supply, default)

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| IN | GND | 1u_0402_X7R | 1 | DS Sec 8.2.2: 1uF input cap |
| OUT | GND | 1u_0402_X7R | 1 | DS Sec 8.2.2: 1uF output cap (min 1uF for stability) |
| OUT | GND | 100n_0402_X7R | 1 | DS Sec 8.2.2: HF bypass on output for transient response |
| EN | IN | 100k_0402_1% | 1 | DS Sec 8.3.3: EN pull-up to IN for always-on (or GPIO control) |
| NR_SS | GND | 10n_0402_X7R | 1 | DS Sec 7.5: 10nF NR/SS cap for low-noise startup (optional but recommended) |

### Pin overrides

_None._

### Layout notes

- Place 1uF output cap within 5mm of OUT pin for 3.3V stability (rule) — _DS Sec 10.2 Layout_

## U2 — TLV75725PDBVR

**Block:** power  
**Datasheet:** [TLV75725PDBVR](https://www.ti.com/lit/ds/symlink/tlv757p.pdf) (Figure 18 - Typical Application, p.18, Figure 18)  
**Footprint:** Package_TO_SOT_SMD:SOT-23-5  
**Min-circuit verified:** yes  

2.5V 1A LDO (VCCO bank supply, alternate)

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| IN | GND | 1u_0402_X7R | 1 | DS Sec 8.2.2: 1uF input cap |
| OUT | GND | 1u_0402_X7R | 1 | DS Sec 8.2.2: 1uF output cap (min 1uF for stability) |
| OUT | GND | 100n_0402_X7R | 1 | DS Sec 8.2.2: HF bypass on output for transient response |
| EN | IN | 100k_0402_1% | 1 | DS Sec 8.3.3: EN pull-up to IN for always-on (or GPIO control) |
| NR_SS | GND | 10n_0402_X7R | 1 | DS Sec 7.5: 10nF NR/SS cap for low-noise startup (optional but recommended) |

### Pin overrides

_None._

### Layout notes

- Place 1uF output cap within 5mm of OUT pin for 2.5V stability (rule) — _DS Sec 10.2 Layout_

## U3 — TLV75718PDBVR

**Block:** power  
**Datasheet:** [TLV75718PDBVR](https://www.ti.com/lit/ds/symlink/tlv757p.pdf) (Figure 18 - Typical Application, p.18, Figure 18)  
**Footprint:** Package_TO_SOT_SMD:SOT-23-5  
**Min-circuit verified:** yes  

1.8V 1A LDO (VCCO bank supply, alternate)

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| IN | GND | 1u_0402_X7R | 1 | DS Sec 8.2.2: 1uF input cap |
| OUT | GND | 1u_0402_X7R | 1 | DS Sec 8.2.2: 1uF output cap (min 1uF for stability) |
| OUT | GND | 100n_0402_X7R | 1 | DS Sec 8.2.2: HF bypass on output for transient response |
| EN | IN | 100k_0402_1% | 1 | DS Sec 8.3.3: EN pull-up to IN for always-on (or GPIO control) |
| NR_SS | GND | 10n_0402_X7R | 1 | DS Sec 7.5: 10nF NR/SS cap for low-noise startup (optional but recommended) |

### Pin overrides

_None._

### Layout notes

- Place 1uF output cap within 5mm of OUT pin for 1.8V stability (rule) — _DS Sec 10.2 Layout_

## U1 — INA226AIDGSR

**Block:** power_mon  
**Datasheet:** [INA226AIDGSR](https://www.ti.com/lit/ds/symlink/ina226.pdf) (Figure 32 - Typical Application Circuit, p.32, Figure 32)  
**Footprint:** Package_SO:VSSOP-10_3x3mm_P0.5mm  
**Min-circuit verified:** yes  

Bidirectional I2C current/power monitor 16-bit, 36V common-mode

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| IN+ | IN- | R_SENSE_10mR_2010_1% | 1 | DS Sec 9.3 + Eq 7: R_SENSE = V_FS / I_max; 10 milliohm gives 81.92mV full-scale at 8.192A (20mV/2.5uV/LSB resolution = INA226 native range) |
| VS | GND | 100n_0402_X7R | 1 | DS Sec 9.2: VS decoupling - 100nF close to pin |
| IN+ | SHUNT_PLUS | 10R_0402_1% | 1 | DS Fig 32: 10 ohm series input filter on IN+ |
| IN+ | IN- | 100n_0402_X7R | 1 | DS Sec 9.3 + Fig 32: Differential filter cap between IN+ / IN- (noise immunity) |

### Pin overrides

_None._

### No external required

_Pins explicitly left bare:_ ALERT

### Layout notes

- Kelvin-sense the shunt: route IN+ / IN- as differential Kelvin connections from each side of the shunt resistor (rule) — _DS Sec 11 Layout - required for sub-mV accuracy_
- Place R_sense in the high-side of the rail (between source and load) (rule) — _DS Sec 9.3 Application_

## U1 — FUSB302BMPX

**Block:** usb_pd  
**Datasheet:** [FUSB302BMPX](https://www.onsemi.com/pdf/datasheet/fusb302b-d.pdf) (Figure 5 - Typical Application Schematic, p.22, Figure 5)  
**Footprint:** Package_DFN_QFN:WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm  
**Supply rail:** +3V3  
**Min-circuit verified:** yes  

USB Type-C / PD CC controller, I2C-controlled

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| VDD | GND | 1u_0402_X7R | 1 | DS 8.2.2 VDD bulk |
| VDD | GND | 100n_0402_X7R | 1 | DS 8.2.2 VDD bypass |
| VBUS | GND | 100n_0402_X7R | 1 | DS Fig 5 VBUS bypass |
| VBUS | +VIN | 1M_0402_1% | 1 | DS Fig 5 VBUS sense divider upper leg (R1) |
| VBUS | GND | 100k_0402_1% | 1 | DS Fig 5 VBUS sense divider lower leg (R2) |
| CC1 | GND | 200p_0402_C0G | 1 | USB-PD cReceiver, DS Fig 5 |
| CC2 | GND | 200p_0402_C0G | 1 | USB-PD cReceiver, DS Fig 5 |
| VCONN_1 | GND | 10u_0603_X7R | 1 | Type-C VCONN bulk per EVB |
| VCONN_2 | GND | 10u_0603_X7R | 1 | Type-C VCONN bulk per EVB |
| SDA | +3V3_SC | 4k7_0402_1% | 1 | DS 7.2 I2C pull-up |
| SCL | +3V3_SC | 4k7_0402_1% | 1 | DS 7.2 I2C pull-up |
| INT_N | +3V3_SC | 10k_0402_1% | 1 | DS 7.2 INT_N pull-up |

### Pin overrides

| Pin | Net |
|---|---|
| CC1 | STM32_USB_CC1 |
| CC2 | STM32_USB_CC2 |
| VDD | +3V3 |
| VBUS | +VIN |
| SDA | STM32_I2C2_SDA |
| SCL | STM32_I2C2_SCL |
| INT_N | STM32_FUSB302_INT |

### Layout notes

- Place 1uF VDD cap within 5mm of pin 3; star-ground EP to PCB GND plane (rule) — _DS Sec 10.2 Layout_
- CC1/CC2 traces: 90 ohm differential impedance, matched length within 5mm (rule) — _USB-C R2.0 Sec 3.2.1_
- VBUS trace from USB-C connector to FUSB302 VBUS pin: keep <= 10mm (guideline) — _Minimize VBUS sense latency_

## U2 — USBLC6-4SC6

**Block:** usb_pd  
**Datasheet:** [USBLC6-4SC6](https://www.st.com/resource/en/datasheet/usblc6-4.pdf) (Figure 1 - Pin connection / Figure 13 - Application, Figure 1 - Pin connection / Figure 13 - Application)  
**Footprint:** Package_TO_SOT_SMD:SOT-23-6  
**Min-circuit verified:** yes  

USB 2.0 ESD/TVS protection, 4 lines, SOT-23-6

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| VBUS | GND | 100n_0402_X7R | 1 | DS Fig 13: VBUS decoupling cap |

### Pin overrides

| Pin | Net |
|---|---|
| I/O1 | USB_DP |
| I/O2 | USB_DM |

### No external required

_Pins explicitly left bare:_ I/O1, I/O2, I/O3, I/O4

### Layout notes

- Place USBLC6 within 5mm of the USB connector pins to minimize stub length (rule) — _DS Sec 4 Layout - protection must precede device_
- Route USB D+/D- as 90 ohm differential pair with length match within 5mm (rule) — _USB 2.0 spec Sec 7.1.6_

## U1 — TPS2051CDBVR

**Block:** usbc_otg  
**Datasheet:** [TPS2051CDBVR](https://www.ti.com/lit/ds/symlink/tps2051c.pdf) (Figure 8-1 - Typical Application Circuit, Figure 8-1 - Typical Application Circuit)  
**Footprint:** Package_TO_SOT_SMD:SOT-23-5  
**Min-circuit verified:** yes  

USB current-limited load switch 0.5A, SOT-23-5

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| IN | GND | 1u_0402_X7R | 1 | DS Sec 8.2.2.1: 1uF ceramic on IN pin |
| OUT | GND | 100u_1206_X5R | 1 | DS Sec 8.2.2.1: 1-150uF on OUT pin; meets USB 2.0 Vbus capacitance |
| OC_N | +3V3 | 10k_0402_1% | 1 | DS Sec 7.3.2: /OC is open-drain, requires pull-up to logic supply |
| EN_N | +3V3 | 10k_0402_1% | 1 | DS Sec 7.3.1: /EN default state high (disabled); GPIO pulls low to enable |

### Pin overrides

_None._

### Layout notes

- Output cap >= 1uF, <= 150uF; place close to OUT pin for transient response (rule) — _DS Sec 8.2.2.1_

## U1 — CP2102N-A02-GQFN24R

**Block:** uart_bridge  
**Datasheet:** [CP2102N-A02-GQFN24R](https://www.silabs.com/documents/public/data-sheets/cp2102n-datasheet.pdf) (Figure 4-1 - Typical USB to UART Bridge, Figure 4-1 - Typical USB to UART Bridge)  
**Footprint:** Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm  
**Min-circuit verified:** yes  

USB to UART bridge, USB 2.0 FS, internal regulator and oscillator

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| VBUS | GND | 100n_0402_X7R | 1 | DS Sec 4.4: VBUS decoupling cap |
| VDD | GND | 4u7_0402_X5R | 1 | DS Fig 4-1: 4.7uF VDD bulk cap (recommended for USB compliance) |
| VDD | GND | 100n_0402_X7R | 1 | DS Fig 4-1: 100nF VDD high-frequency bypass |
| REGIN | GND | 1u_0402_X7R | 1 | DS Sec 4.3: REGIN bypass cap when using internal regulator |
| RST_N | VDD | 10k_0402_1% | 1 | DS Sec 4.5: RST_N requires pull-up to VDD |
| RST_N | GND | 100n_0402_X7R | 1 | DS Sec 4.5: 100nF RST_N filter to GND for noise immunity |

### Pin overrides

_None._

### No external required

_Pins explicitly left bare:_ D+, D-, RXD, TXD

### Layout notes

- Place D+/D- matched length to USB-C connector, 90 ohm differential impedance (rule) — _USB 2.0 Sec 7.1.6_
- Connect exposed pad (EP) to GND plane with multiple vias for thermal dissipation (rule) — _DS Sec 11.1 Layout_

## U1 — TPD12S016PWR

**Block:** hdmi_tx  
**Datasheet:** [TPD12S016PWR](https://www.ti.com/lit/ds/symlink/tpd12s016.pdf) (Figure 13 - HDMI Source Application, Figure 13 - HDMI Source Application)  
**Footprint:** Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm  
**Min-circuit verified:** yes  

HDMI source companion: ESD + I2C/HPD level shift + 5V switch

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| VCCA | GND | 1u_0402_X7R | 1 | DS Sec 9.2: VCCA (5V) bulk decoupling |
| VCCA | GND | 100n_0402_X7R | 1 | DS Sec 9.2: VCCA HF bypass |
| VCCB | GND | 1u_0402_X7R | 1 | DS Sec 9.2: VCCB (3.3V logic) bulk decoupling |
| VCCB | GND | 100n_0402_X7R | 1 | DS Sec 9.2: VCCB HF bypass |
| SDA_B | +3V3 | 4k7_0402_1% | 1 | DS Sec 8.3.3: I2C MCU-side pull-up to VCCB |
| SCL_B | +3V3 | 4k7_0402_1% | 1 | DS Sec 8.3.3: I2C MCU-side pull-up to VCCB |
| HPD_B | GND | 100k_0402_1% | 1 | DS Sec 8.3.4: HPD_B pull-down (MCU input) |
| CT_CP_HPD | +3V3 | 10k_0402_1% | 1 | DS Sec 8.3.4: CT_CP_HPD GPIO controls direction + 5V switch |

### Pin overrides

_None._

### No external required

_Pins explicitly left bare:_ CLK+, CLK-, D0+, D0-, D1+, D1-, D2+, D2-

### Layout notes

- Place TPD12S016 between HDMI connector and Zynq PL within 20mm of connector (rule) — _DS Sec 11.1 - ESD protection must precede device_
- TMDS pairs: 100 ohm differential, length-match within 0.5mm across pairs (rule) — _HDMI 1.4 Sec 4.2.3_

## U2 — 24LC256T-I/SN

**Block:** hdmi_tx  
**Datasheet:** [24LC256T-I/SN](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/21203P.pdf) (Figure 4-1 + HDMI DDC EDID wiring, DS21203P Fig 4-1 + HDMI DDC at +5V)  
**Footprint:** Package_SO:SOIC-8_3.9x4.9mm_P1.27mm  
**Supply rail:** +5V  
**Min-circuit verified:** yes  

256 Kbit I2C EDID EEPROM on HDMI DDC bus

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| VCC | GND | 100n_0402_X7R | 1 | DS Sec 2.0: VCC decoupling cap |
| SDA | +5V | 2k2_0402_1% | 1 | HDMI DDC SDA pull-up to +5V (shared with connector) |
| SCL | +5V | 2k2_0402_1% | 1 | HDMI DDC SCL pull-up to +5V (shared with connector) |

### Pin overrides

_None._

### Strap pins

| Pin | Tied to | Purpose | Why |
|---|---|---|---|
| A0 | GND | EDID I2C address bit 0 = 0 | DS Sec 5.1 |
| A1 | +5V | EDID I2C address bit 1 = 1 (address 0x54) | HDMI EDID typical address 0xA0/0xA1 |
| A2 | GND | EDID I2C address bit 2 = 0 | DS Sec 5.1 |
| WP | GND | Write protect disabled for EDID programming | DS Sec 7.0 |

### Layout notes

- Route DDC SDA/SCL to HDMI connector within 20mm (rule)

## U1 — TPD12S016PWR

**Block:** hdmi_rx  
**Datasheet:** [TPD12S016PWR](https://www.ti.com/lit/ds/symlink/tpd12s016.pdf) (Figure 14 - HDMI Sink Application, Figure 14 - HDMI Sink Application)  
**Footprint:** Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm  
**Min-circuit verified:** yes  

HDMI sink companion: ESD + I2C/HPD level shift (no 5V switch)

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| VCCA | GND | 1u_0402_X7R | 1 | DS Sec 9.2: VCCA (5V) bulk decoupling |
| VCCA | GND | 100n_0402_X7R | 1 | DS Sec 9.2: VCCA HF bypass |
| VCCB | GND | 1u_0402_X7R | 1 | DS Sec 9.2: VCCB (3.3V logic) bulk decoupling |
| VCCB | GND | 100n_0402_X7R | 1 | DS Sec 9.2: VCCB HF bypass |
| SDA_B | +3V3 | 4k7_0402_1% | 1 | DS Sec 8.3.3: I2C MCU-side pull-up to VCCB |
| SCL_B | +3V3 | 4k7_0402_1% | 1 | DS Sec 8.3.3: I2C MCU-side pull-up to VCCB |
| HPD_B | GND | 100k_0402_1% | 1 | DS Sec 8.3.4: HPD_B pull-down (MCU input) |
| CT_CP_HPD | +3V3 | 10k_0402_1% | 1 | DS Sec 8.3.4: CT_CP_HPD always-on for sink mode |

### Pin overrides

_None._

### No external required

_Pins explicitly left bare:_ CLK+, CLK-, D0+, D0-, D1+, D1-, D2+, D2-

### Layout notes

- HDMI RX 5V comes from connected source, not generated locally
- TMDS RX termination: 50 ohm to AVCC inside Zynq RX block; do NOT add external Rs (rule) — _HDMI 1.4 Sec 4.2.5_

## T1 — HX5008NLT

**Block:** ethernet  
**Datasheet:** [HX5008NLT](https://productfinder.pulseeng.com/files/datasheets/HX5008NL.pdf) (Figure 1 - Application Schematic (1000BASE-T), p.4, Figure 1 + IEEE 802.3 Bob Smith)  
**Footprint:** Package_SO:SOIC-24W_7.5x15.4mm_P1.27mm  
**Min-circuit verified:** yes  

1000BASE-T 4-pair Ethernet magnetics module, SOIC-24

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| CT_PAIR0 | BS_COMMON | 75R_0603_1% | 1 | IEEE 802.3 Bob Smith termination, pair 0 center tap |
| CT_PAIR0 | BS_COMMON | 1n_2kV_0603_safety | 1 | IEEE 802.3 Bob Smith 1nF per pair, pair 0 |
| CT_PAIR1 | BS_COMMON | 75R_0603_1% | 1 | IEEE 802.3 Bob Smith termination, pair 1 center tap |
| CT_PAIR1 | BS_COMMON | 1n_2kV_0603_safety | 1 | IEEE 802.3 Bob Smith 1nF per pair, pair 1 |
| CT_PAIR2 | BS_COMMON | 75R_0603_1% | 1 | IEEE 802.3 Bob Smith termination, pair 2 center tap |
| CT_PAIR2 | BS_COMMON | 1n_2kV_0603_safety | 1 | IEEE 802.3 Bob Smith 1nF per pair, pair 2 |
| CT_PAIR3 | BS_COMMON | 75R_0603_1% | 1 | IEEE 802.3 Bob Smith termination, pair 3 center tap |
| CT_PAIR3 | BS_COMMON | 1n_2kV_0603_safety | 1 | IEEE 802.3 Bob Smith 1nF per pair, pair 3 |
| BS_COMMON | CHASSIS_GND | 1n_2kV_0603_safety | 1 | IEEE 802.3 / EN 55032: 1nF/2kV common-mode cap to chassis GND |

### Pin overrides

_None._

### No external required

_Pins explicitly left bare:_ MDI0_N, MDI0_P, MDI1_N, MDI1_P, MDI2_N, MDI2_P, MDI3_N, MDI3_P, TD0_N, TD0_P, TD1_N, TD1_P, TD2_N, TD2_P, TD3_N, TD3_P

### Layout notes

- Route each MDI pair as 100 ohm differential impedance, matched length within 0.5mm (rule) — _IEEE 802.3 / Pulse layout guide_
- Chassis GND must be isolated from signal GND - join only at one point near RJ45 (rule) — _EMI compliance_
- Place magnetics module within 30mm of RJ45 connector (rule) — _Reduce common-mode noise_

## SW1 — DS-04P

**Block:** boot_switches  
**Datasheet:** [DS-04P](https://datasheet.lcsc.com/lcsc/Hanbo-Electronic-DS-04P_C18198092.pdf) (Boot mode strap switches, Zynq boot mode: pull-up on each strap bit)  
**Footprint:** Switch_SMD:DIP_Switch_x4  
**Supply rail:** +3V3  
**Min-circuit verified:** yes  

4-position 1.27mm DIP boot mode switch

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| SW1 | +3V3 | 10k_0402_1% | 1 | Boot strap bit 0 pull-up (switch to GND when ON) |
| SW2 | +3V3 | 10k_0402_1% | 1 | Boot strap bit 1 pull-up |
| SW3 | +3V3 | 10k_0402_1% | 1 | Boot strap bit 2 pull-up |
| SW4 | +3V3 | 10k_0402_1% | 1 | Boot strap bit 3 pull-up |

### Pin overrides

| Pin | Net |
|---|---|
| SW1 | ZYNQ_BOOT_MODE_0 |
| SW2 | ZYNQ_BOOT_MODE_1 |
| SW3 | ZYNQ_BOOT_MODE_2 |
| SW4 | ZYNQ_BOOT_MODE_3 |

### Layout notes

_None recorded._

## SW2 — TS-1002S-06026C

**Block:** boot_switches  
**Datasheet:** [TS-1002S-06026C](https://datasheet.lcsc.com/lcsc/XUNPU-TS-1002S-06026C_C455112.pdf) (Typical tact switch to GPIO, Switch DS + debounce cap to GND)  
**Footprint:** Button_Switch_SMD:SW_SPST_Tactile_6x6mm  
**Supply rail:** +3V3  
**Min-circuit verified:** yes  

6x6mm tactile switch with pull-up and debounce

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| SW | +3V3 | 10k_0402_1% | 1 | Pull-up: switch active-low to GND |
| SW | GND | 100n_0402_X7R | 1 | Debounce / ESD shunt at switch node |

### Pin overrides

| Pin | Net |
|---|---|
| SW | ZYNQ_PS_SRST_N |

### Layout notes

_None recorded._
