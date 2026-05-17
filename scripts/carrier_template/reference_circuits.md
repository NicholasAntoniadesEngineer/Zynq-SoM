# Carrier Reference Circuits

Auto-generated design intent record. For every IC on the carrier, this document shows the manufacturer reference circuit applied: every external part required by the datasheet, strap pin states, layout notes, and explicit no-external-required pins.

This document is reviewed by the EE before PCB tape-out to confirm the carrier design follows each IC's reference design.

## Contents

- [FUSB302BMPX](#fusb302bmpx)
- [USBLC6-4SC6](#usblc6-4sc6)
- [TPS2051CDBVR](#tps2051cdbvr)
- [TPD12S016PWR_TX](#tpd12s016pwr_tx)
- [TPD12S016PWR_RX](#tpd12s016pwr_rx)
- [CP2102N-A02-GQFN24R](#cp2102n-a02-gqfn24r)
- [INA226AIDGSR](#ina226aidgsr)
- [DS3231SN#](#ds3231sn#)
- [24LC256T-I/SN](#24lc256t-isn)
- [TLV75718PDBVR](#tlv75718pdbvr)
- [TLV75725PDBVR](#tlv75725pdbvr)
- [TLV75733PDBVR](#tlv75733pdbvr)
- [HX5008NLT](#hx5008nlt)
- [USBC_SINK](#usbc_sink)
- [HDMI_A](#hdmi_a)
- [DM3AT-SF-PEJM5](#dm3at-sf-pejm5)
- [RJHSE5380](#rjhse5380)

---

## FUSB302BMPX

- **Function**: USB Type-C / PD CC controller, I2C-controlled
- **LCSC**: [C442699](https://www.lcsc.com/product-detail/C442699.html)
- **Footprint**: `Package_DFN_QFN:WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm` (WQFN-14)
- **Stock at LCSC**: 5,262
- **Unit price**: $0.8100
- **Datasheet**: [Rev 6, May 2020](https://www.onsemi.com/pdf/datasheet/fusb302b-d.pdf)
- **Reference design citation**: Figure 5 - Typical Application Schematic
- **Instances on carrier**: 1

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `VDD` | `GND` | `1u_0402_X7R` | 1 | DS Sec 8.2.2: 1uF VDD bulk decoupling, place within 5mm |
| `VDD` | `GND` | `100n_0402_X7R` | 1 | DS Sec 8.2.2: 100nF high-frequency VDD bypass |
| `VBUS` | `GND` | `100n_0402_X7R` | 1 | DS Fig 5: VBUS local bypass |
| `SDA` | `+3V3_SC` | `4k7_0402_1%` | 1 | DS Sec 7.2 I2C SDA pull-up to host VIO; one per bus |
| `SCL` | `+3V3_SC` | `4k7_0402_1%` | 1 | DS Sec 7.2 I2C SCL pull-up to host VIO; one per bus |
| `INT_N` | `+3V3_SC` | `10k_0402_1%` | 1 | DS Sec 7.2: INT_N is open-drain, requires pull-up to host VIO |

### Pins requiring no external components (per datasheet)

- `CC1`
- `CC2`
- `VCONN_1`
- `VCONN_2`

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Place 1uF VDD cap within 5mm of pin 3; star-ground EP to PCB GND plane (DS Sec 10.2 Layout)
- **RULE**: CC1/CC2 traces: 90 ohm differential impedance, matched length within 5mm (USB-C R2.0 Sec 3.2.1)
- _guideline_: VBUS trace from USB-C connector to FUSB302 VBUS pin: keep <= 10mm (Minimize VBUS sense latency)

---

## USBLC6-4SC6

- **Function**: USB 2.0 ESD/TVS protection, 4 lines, SOT-23-6
- **LCSC**: [C111212](https://www.lcsc.com/product-detail/C111212.html)
- **Footprint**: `Package_TO_SOT_SMD:SOT-23-6` (SOT-23-6)
- **Stock at LCSC**: 17,280
- **Unit price**: $0.1700
- **Datasheet**: [Rev 11, Mar 2024](https://www.st.com/resource/en/datasheet/usblc6-4.pdf)
- **Reference design citation**: Figure 1 - Pin connection / Figure 13 - Application
- **Instances on carrier**: 2

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `VBUS` | `GND` | `100n_0402_X7R` | 1 | DS Fig 13: VBUS decoupling cap |

### Pins requiring no external components (per datasheet)

- `I/O1`
- `I/O2`
- `I/O3`
- `I/O4`

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Place USBLC6 within 5mm of the USB connector pins to minimize stub length (DS Sec 4 Layout - protection must precede device)
- **RULE**: Route USB D+/D- as 90 ohm differential pair with length match within 5mm (USB 2.0 spec Sec 7.1.6)

---

## TPS2051CDBVR

- **Function**: USB current-limited load switch 0.5A, SOT-23-5
- **LCSC**: [C129581](https://www.lcsc.com/product-detail/C129581.html)
- **Footprint**: `Package_TO_SOT_SMD:SOT-23-5` (SOT-23-5)
- **Stock at LCSC**: 5,460
- **Unit price**: $0.1300
- **Datasheet**: [Rev May 2014](https://www.ti.com/lit/ds/symlink/tps2051c.pdf)
- **Reference design citation**: Figure 8-1 - Typical Application Circuit
- **Instances on carrier**: 1

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `IN` | `GND` | `1u_0402_X7R` | 1 | DS Sec 8.2.2.1: 1uF ceramic on IN pin |
| `OUT` | `GND` | `100u_1206_X5R` | 1 | DS Sec 8.2.2.1: 1-150uF on OUT pin; meets USB 2.0 Vbus capacitance |
| `OC_N` | `+3V3` | `10k_0402_1%` | 1 | DS Sec 7.3.2: /OC is open-drain, requires pull-up to logic supply |
| `EN_N` | `+3V3` | `10k_0402_1%` | 1 | DS Sec 7.3.1: /EN default state high (disabled); GPIO pulls low to enable |

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Output cap >= 1uF, <= 150uF; place close to OUT pin for transient response (DS Sec 8.2.2.1)

---

## TPD12S016PWR

- **Function**: HDMI source companion: ESD + I2C/HPD level shift + 5V switch
- **LCSC**: [C201665](https://www.lcsc.com/product-detail/C201665.html)
- **Footprint**: `Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm` (TSSOP-24)
- **Stock at LCSC**: 900
- **Unit price**: $0.8300
- **Datasheet**: [Rev May 2017](https://www.ti.com/lit/ds/symlink/tpd12s016.pdf)
- **Reference design citation**: Figure 13 - HDMI Source Application
- **Instances on carrier**: 1

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `VCCA` | `GND` | `1u_0402_X7R` | 1 | DS Sec 9.2: VCCA (5V) bulk decoupling |
| `VCCA` | `GND` | `100n_0402_X7R` | 1 | DS Sec 9.2: VCCA HF bypass |
| `VCCB` | `GND` | `1u_0402_X7R` | 1 | DS Sec 9.2: VCCB (3.3V logic) bulk decoupling |
| `VCCB` | `GND` | `100n_0402_X7R` | 1 | DS Sec 9.2: VCCB HF bypass |
| `SDA_B` | `+3V3` | `4k7_0402_1%` | 1 | DS Sec 8.3.3: I2C MCU-side pull-up to VCCB |
| `SCL_B` | `+3V3` | `4k7_0402_1%` | 1 | DS Sec 8.3.3: I2C MCU-side pull-up to VCCB |
| `HPD_B` | `GND` | `100k_0402_1%` | 1 | DS Sec 8.3.4: HPD_B pull-down (MCU input) |
| `CT_CP_HPD` | `+3V3` | `10k_0402_1%` | 1 | DS Sec 8.3.4: CT_CP_HPD GPIO controls direction + 5V switch |

### Pins requiring no external components (per datasheet)

- `CLK+`
- `CLK-`
- `D0+`
- `D0-`
- `D1+`
- `D1-`
- `D2+`
- `D2-`

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Place TPD12S016 between HDMI connector and Zynq PL within 20mm of connector (DS Sec 11.1 - ESD protection must precede device)
- **RULE**: TMDS pairs: 100 ohm differential, length-match within 0.5mm across pairs (HDMI 1.4 Sec 4.2.3)

---

## TPD12S016PWR

- **Function**: HDMI sink companion: ESD + I2C/HPD level shift (no 5V switch)
- **LCSC**: [C201665](https://www.lcsc.com/product-detail/C201665.html)
- **Footprint**: `Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm` (TSSOP-24)
- **Stock at LCSC**: 900
- **Unit price**: $0.8300
- **Datasheet**: [Rev May 2017](https://www.ti.com/lit/ds/symlink/tpd12s016.pdf)
- **Reference design citation**: Figure 14 - HDMI Sink Application
- **Instances on carrier**: 1

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `VCCA` | `GND` | `1u_0402_X7R` | 1 | DS Sec 9.2: VCCA (5V) bulk decoupling |
| `VCCA` | `GND` | `100n_0402_X7R` | 1 | DS Sec 9.2: VCCA HF bypass |
| `VCCB` | `GND` | `1u_0402_X7R` | 1 | DS Sec 9.2: VCCB (3.3V logic) bulk decoupling |
| `VCCB` | `GND` | `100n_0402_X7R` | 1 | DS Sec 9.2: VCCB HF bypass |
| `SDA_B` | `+3V3` | `4k7_0402_1%` | 1 | DS Sec 8.3.3: I2C MCU-side pull-up to VCCB |
| `SCL_B` | `+3V3` | `4k7_0402_1%` | 1 | DS Sec 8.3.3: I2C MCU-side pull-up to VCCB |
| `HPD_B` | `GND` | `100k_0402_1%` | 1 | DS Sec 8.3.4: HPD_B pull-down (MCU input) |
| `CT_CP_HPD` | `+3V3` | `10k_0402_1%` | 1 | DS Sec 8.3.4: CT_CP_HPD always-on for sink mode |

### Pins requiring no external components (per datasheet)

- `CLK+`
- `CLK-`
- `D0+`
- `D0-`
- `D1+`
- `D1-`
- `D2+`
- `D2-`

### PCB layout notes (carry forward to PCB stage)

- info: HDMI RX 5V comes from connected source, not generated locally
- **RULE**: TMDS RX termination: 50 ohm to AVCC inside Zynq RX block; do NOT add external Rs (HDMI 1.4 Sec 4.2.5)

---

## CP2102N-A02-GQFN24R

- **Function**: USB to UART bridge, USB 2.0 FS, internal regulator and oscillator
- **LCSC**: [C969151](https://www.lcsc.com/product-detail/C969151.html)
- **Footprint**: `Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm` (QFN-24)
- **Stock at LCSC**: 11,648
- **Unit price**: $1.8900
- **Datasheet**: [Rev 1.5, 2021](https://www.silabs.com/documents/public/data-sheets/cp2102n-datasheet.pdf)
- **Reference design citation**: Figure 4-1 - Typical USB to UART Bridge
- **Instances on carrier**: 1

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `VBUS` | `GND` | `100n_0402_X7R` | 1 | DS Sec 4.4: VBUS decoupling cap |
| `VDD` | `GND` | `4u7_0402_X5R` | 1 | DS Fig 4-1: 4.7uF VDD bulk cap (recommended for USB compliance) |
| `VDD` | `GND` | `100n_0402_X7R` | 1 | DS Fig 4-1: 100nF VDD high-frequency bypass |
| `REGIN` | `GND` | `1u_0402_X7R` | 1 | DS Sec 4.3: REGIN bypass cap when using internal regulator |
| `RST_N` | `VDD` | `10k_0402_1%` | 1 | DS Sec 4.5: RST_N requires pull-up to VDD |
| `RST_N` | `GND` | `100n_0402_X7R` | 1 | DS Sec 4.5: 100nF RST_N filter to GND for noise immunity |

### Pins requiring no external components (per datasheet)

- `D+`
- `D-`
- `RXD`
- `TXD`

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Place D+/D- matched length to USB-C connector, 90 ohm differential impedance (USB 2.0 Sec 7.1.6)
- **RULE**: Connect exposed pad (EP) to GND plane with multiple vias for thermal dissipation (DS Sec 11.1 Layout)

---

## INA226AIDGSR

- **Function**: Bidirectional I2C current/power monitor 16-bit, 36V common-mode
- **LCSC**: [C49851](https://www.lcsc.com/product-detail/C49851.html)
- **Footprint**: `Package_SO:VSSOP-10_3x3mm_P0.5mm` (VSSOP-10)
- **Stock at LCSC**: 5,462
- **Unit price**: $0.7000
- **Datasheet**: [Rev August 2015 (SBOS547A)](https://www.ti.com/lit/ds/symlink/ina226.pdf)
- **Reference design citation**: Figure 32 - Typical Application Circuit
- **Instances on carrier**: 6

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `IN+` | `IN-` | `R_SENSE_10mR_2010_1%` | 1 | DS Sec 9.3 + Eq 7: R_SENSE = V_FS / I_max; 10 milliohm gives 81.92mV full-scale at 8.192A (20mV/2.5uV/LSB resolution = INA226 native range) |
| `VS` | `GND` | `100n_0402_X7R` | 1 | DS Sec 9.2: VS decoupling - 100nF close to pin |
| `IN+` | `IN-` | `100n_0402_X7R` | 1 | DS Sec 9.3 + Fig 32: Differential filter cap between IN+ / IN- (noise immunity) |

### Pins requiring no external components (per datasheet)

- `ALERT`

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Kelvin-sense the shunt: route IN+ / IN- as differential Kelvin connections from each side of the shunt resistor (DS Sec 11 Layout - required for sub-mV accuracy)
- **RULE**: Place R_sense in the high-side of the rail (between source and load) (DS Sec 9.3 Application)

---

## DS3231SN#

- **Function**: Accurate I2C RTC with internal TCXO, battery backup, SOIC-16W
- **LCSC**: [C722469](https://www.lcsc.com/product-detail/C722469.html)
- **Footprint**: `Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm` (SOIC-16W)
- **Stock at LCSC**: 82
- **Unit price**: $7.1200
- **Datasheet**: [Rev 10, 2015](https://www.analog.com/media/en/technical-documentation/data-sheets/DS3231.pdf)
- **Reference design citation**: Figure 1 - Typical Operating Circuit
- **Instances on carrier**: 1

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `VCC` | `GND` | `100n_0402_X7R` | 1 | DS Fig 1: 100nF VCC decoupling |
| `VBAT` | `GND` | `100n_0402_X7R` | 1 | DS Fig 1: 100nF VBAT decoupling for noise immunity |
| `SDA` | `+3V3` | `4k7_0402_1%` | 1 | DS Sec Electrical Characteristics: I2C pull-up (one per bus) |
| `SCL` | `+3V3` | `4k7_0402_1%` | 1 | DS Sec Electrical Characteristics: I2C pull-up (one per bus) |
| `RST_N` | `VCC` | `10k_0402_1%` | 1 | DS Sec Power Control: RST_N is open-drain, requires pull-up |
| `32kHz` | `VCC` | `10k_0402_1%` | 1 | DS Sec 32kHz Output: open-drain pull-up if 32kHz used |
| `INT_SQW` | `VCC` | `10k_0402_1%` | 1 | DS Sec INT/SQW Output: open-drain pull-up |

### Pins requiring no external components (per datasheet)

- `10`
- `11`
- `12`
- `5`
- `6`
- `7`
- `8`
- `9`

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Connect VBAT to CR2032 backup battery through a 10k current-limit resistor (DS Fig 1) (DS Power Control section)
- _guideline_: Keep VBAT and VCC bypass caps close to the IC for low ESR

---

## 24LC256T-I/SN

- **Function**: 256 Kbit I2C Serial EEPROM, SOIC-8
- **LCSC**: [C5458](https://www.lcsc.com/product-detail/C5458.html)
- **Footprint**: `Package_SO:SOIC-8_3.9x4.9mm_P1.27mm` (SOIC-8)
- **Stock at LCSC**: 17,726
- **Unit price**: $0.5800
- **Datasheet**: [Rev May 2020 (DS21203P)](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/21203P.pdf)
- **Reference design citation**: Figure 4-1 - Typical Application Circuit
- **Instances on carrier**: 2

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `VCC` | `GND` | `100n_0402_X7R` | 1 | DS Sec 2.0 Electrical Characteristics: VCC decoupling cap |
| `SDA` | `+3V3` | `4k7_0402_1%` | 1 | DS Sec 4.2: I2C SDA pull-up (one per bus) |
| `SCL` | `+3V3` | `4k7_0402_1%` | 1 | DS Sec 4.2: I2C SCL pull-up (one per bus) |

### Strap pin configuration

| Pin | Tied to | Purpose | Justification |
|---|---|---|---|
| `A0` | `GND` | I2C address bit 0 = 0 | DS Sec 5.1 Slave Address |
| `A1` | `GND` | I2C address bit 1 = 0 | DS Sec 5.1 Slave Address |
| `A2` | `GND` | I2C address bit 2 = 0 (default address 0x50) | DS Sec 5.1 Slave Address |
| `WP` | `GND` | Write protect disabled (write-enabled) | DS Sec 7.0 Write Protection |

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Keep VCC decoupling within 5mm of pin 8

---

## TLV75718PDBVR

- **Function**: 1.8V 1A LDO (VCCO bank supply, alternate)
- **LCSC**: [C507270](https://www.lcsc.com/product-detail/C507270.html)
- **Footprint**: `Package_TO_SOT_SMD:SOT-23-5` (SOT-23-5)
- **Stock at LCSC**: 167
- **Unit price**: $0.2700
- **Datasheet**: [Rev Sep 2017](https://www.ti.com/lit/ds/symlink/tlv757p.pdf)
- **Reference design citation**: Figure 18 - Typical Application
- **Instances on carrier**: 0

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `IN` | `GND` | `1u_0402_X7R` | 1 | DS Sec 8.2.2: 1uF input cap |
| `OUT` | `GND` | `1u_0402_X7R` | 1 | DS Sec 8.2.2: 1uF output cap (min 1uF for stability) |
| `OUT` | `GND` | `100n_0402_X7R` | 1 | DS Sec 8.2.2: HF bypass on output for transient response |
| `EN` | `IN` | `100k_0402_1%` | 1 | DS Sec 8.3.3: EN pull-up to IN for always-on (or GPIO control) |
| `NR_SS` | `GND` | `10n_0402_X7R` | 1 | DS Sec 7.5: 10nF NR/SS cap for low-noise startup (optional but recommended) |

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Place 1uF output cap within 5mm of OUT pin for 1.8V stability (DS Sec 10.2 Layout)

---

## TLV75725PDBVR

- **Function**: 2.5V 1A LDO (VCCO bank supply, alternate)
- **LCSC**: [C2872563](https://www.lcsc.com/product-detail/C2872563.html)
- **Footprint**: `Package_TO_SOT_SMD:SOT-23-5` (SOT-23-5)
- **Stock at LCSC**: 500
- **Unit price**: $0.2700
- **Datasheet**: [Rev Sep 2017](https://www.ti.com/lit/ds/symlink/tlv757p.pdf)
- **Reference design citation**: Figure 18 - Typical Application
- **Instances on carrier**: 0

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `IN` | `GND` | `1u_0402_X7R` | 1 | DS Sec 8.2.2: 1uF input cap |
| `OUT` | `GND` | `1u_0402_X7R` | 1 | DS Sec 8.2.2: 1uF output cap (min 1uF for stability) |
| `OUT` | `GND` | `100n_0402_X7R` | 1 | DS Sec 8.2.2: HF bypass on output for transient response |
| `EN` | `IN` | `100k_0402_1%` | 1 | DS Sec 8.3.3: EN pull-up to IN for always-on (or GPIO control) |
| `NR_SS` | `GND` | `10n_0402_X7R` | 1 | DS Sec 7.5: 10nF NR/SS cap for low-noise startup (optional but recommended) |

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Place 1uF output cap within 5mm of OUT pin for 2.5V stability (DS Sec 10.2 Layout)

---

## TLV75733PDBVR

- **Function**: 3.3V 1A LDO (VCCO bank supply, default)
- **LCSC**: [C485517](https://www.lcsc.com/product-detail/C485517.html)
- **Footprint**: `Package_TO_SOT_SMD:SOT-23-5` (SOT-23-5)
- **Stock at LCSC**: 65,240
- **Unit price**: $0.2700
- **Datasheet**: [Rev Sep 2017](https://www.ti.com/lit/ds/symlink/tlv757p.pdf)
- **Reference design citation**: Figure 18 - Typical Application
- **Instances on carrier**: 4

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `IN` | `GND` | `1u_0402_X7R` | 1 | DS Sec 8.2.2: 1uF input cap |
| `OUT` | `GND` | `1u_0402_X7R` | 1 | DS Sec 8.2.2: 1uF output cap (min 1uF for stability) |
| `OUT` | `GND` | `100n_0402_X7R` | 1 | DS Sec 8.2.2: HF bypass on output for transient response |
| `EN` | `IN` | `100k_0402_1%` | 1 | DS Sec 8.3.3: EN pull-up to IN for always-on (or GPIO control) |
| `NR_SS` | `GND` | `10n_0402_X7R` | 1 | DS Sec 7.5: 10nF NR/SS cap for low-noise startup (optional but recommended) |

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Place 1uF output cap within 5mm of OUT pin for 3.3V stability (DS Sec 10.2 Layout)

---

## HX5008NLT

- **Function**: 1000BASE-T 4-pair Ethernet magnetics module, SOIC-24
- **LCSC**: [C962544](https://www.lcsc.com/product-detail/C962544.html)
- **Footprint**: `Package_SO:SOIC-24W_7.5x15.4mm_P1.27mm` (SOIC-24-15.1mm)
- **Stock at LCSC**: 2,328
- **Unit price**: $1.7800
- **Datasheet**: [Rev 2.2](https://productfinder.pulseeng.com/files/datasheets/HX5008NL.pdf)
- **Reference design citation**: Figure 1 - Application Schematic (1000BASE-T)
- **Instances on carrier**: 1

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `CT_PAIR0` | `BS_COMMON` | `75R_0603_1%` | 1 | IEEE 802.3 Bob Smith termination, pair 0 center tap |
| `CT_PAIR1` | `BS_COMMON` | `75R_0603_1%` | 1 | IEEE 802.3 Bob Smith termination, pair 1 center tap |
| `CT_PAIR2` | `BS_COMMON` | `75R_0603_1%` | 1 | IEEE 802.3 Bob Smith termination, pair 2 center tap |
| `CT_PAIR3` | `BS_COMMON` | `75R_0603_1%` | 1 | IEEE 802.3 Bob Smith termination, pair 3 center tap |
| `BS_COMMON` | `CHASSIS_GND` | `1n_2kV_0603_safety` | 1 | IEEE 802.3 / EN 55032: 1nF/2kV common-mode cap to chassis GND |

### Pins requiring no external components (per datasheet)

- `MDI0_N`
- `MDI0_P`
- `MDI1_N`
- `MDI1_P`
- `MDI2_N`
- `MDI2_P`
- `MDI3_N`
- `MDI3_P`
- `TD0_N`
- `TD0_P`
- `TD1_N`
- `TD1_P`
- `TD2_N`
- `TD2_P`
- `TD3_N`
- `TD3_P`

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Route each MDI pair as 100 ohm differential impedance, matched length within 0.5mm (IEEE 802.3 / Pulse layout guide)
- **RULE**: Chassis GND must be isolated from signal GND - join only at one point near RJ45 (EMI compliance)
- **RULE**: Place magnetics module within 30mm of RJ45 connector (Reduce common-mode noise)

---

## TYPE-C-31-M-12

- **Function**: USB Type-C 16P SMD receptacle, configured as sink/device
- **LCSC**: [C165948](https://www.lcsc.com/product-detail/C165948.html)
- **Footprint**: `Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12` (USB-C SMD)
- **Stock at LCSC**: 263,165
- **Unit price**: $0.1700
- **Datasheet**: [2023](https://datasheet.lcsc.com/lcsc/2304140030_Korean-Hroparts-Elec-TYPE-C-31-M-12_C165948.pdf)
- **Reference design citation**: USB Type-C R2.0 Sec 3.4.4 - Sink Configuration
- **Instances on carrier**: 2

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `CC1` | `GND` | `5k1_0402_1%` | 1 | USB-C R2.0 Sec 4.5: 5.1k Rd advertises sink role |
| `CC2` | `GND` | `5k1_0402_1%` | 1 | USB-C R2.0 Sec 4.5: 5.1k Rd on each CC for reversibility |
| `VBUS` | `GND` | `10u_0402_X5R` | 1 | USB-PD Sec 7.1.6: VBUS bulk capacitance |
| `VBUS` | `GND` | `100n_0402_X7R` | 1 | USB 2.0 Sec 7.1.6.1: VBUS HF bypass |
| `SHIELD` | `CHASSIS_GND` | `1M_0402_1%` | 1 | USB-IF Compliance: 1M shield-to-GND discharge resistor |
| `SHIELD` | `CHASSIS_GND` | `100n_0402_X7R` | 1 | USB-IF Compliance: 100nF shield AC-coupling to chassis |

### Pins requiring no external components (per datasheet)

- `D+`
- `D-`
- `RX1+`
- `RX1-`
- `SBU1`
- `SBU2`
- `TX1+`
- `TX1-`

### PCB layout notes (carry forward to PCB stage)

- **RULE**: USB 2.0 D+/D- routing: 90 ohm differential impedance, matched length within 5mm (USB 2.0 Sec 7.1.6)
- **RULE**: VBUS routing: minimum 0.3mm trace width for >= 1A current (IPC-2221 current carrying capacity)
- **RULE**: Connect connector mounting tabs to CHASSIS_GND only (not signal GND) (EMI compliance)

---

## HDMI-019S

- **Function**: HDMI Type-A receptacle, 19 pin
- **LCSC**: [C111617](https://www.lcsc.com/product-detail/C111617.html)
- **Footprint**: `Connector_HDMI:HDMI_A_SOFNG_HDMI-019S` (HDMI Type-A SMD)
- **Stock at LCSC**: 10,535
- **Unit price**: $0.2100
- **Datasheet**: [2022](https://datasheet.lcsc.com/lcsc/SOFNG-HDMI-019S_C111617.pdf)
- **Reference design citation**: HDMI 1.4 Sec 4.2 / TPD12S016 DS Fig 13-14
- **Instances on carrier**: 2

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `+5V` | `GND` | `100n_0402_X7R` | 1 | HDMI Sec 4.2.7: 5V bypass at connector |
| `CEC` | `+3V3` | `10k_0402_1%` | 1 | HDMI 1.4 Sec 5.1: CEC line idle-high via pull-up |
| `SHIELD` | `CHASSIS_GND` | `1M_0402_1%` | 1 | HDMI 1.4 Sec 4.2.7: shield discharge to chassis |
| `SHIELD` | `CHASSIS_GND` | `100n_0402_X7R` | 1 | HDMI 1.4 Sec 4.2.7: shield AC bypass to chassis |

### Pins requiring no external components (per datasheet)

- `TMDS_CLK+`
- `TMDS_CLK-`
- `TMDS_D0+`
- `TMDS_D0-`
- `TMDS_D1+`
- `TMDS_D1-`
- `TMDS_D2+`
- `TMDS_D2-`

### PCB layout notes (carry forward to PCB stage)

- **RULE**: TMDS pairs: 100 ohm differential impedance, length-matched within 0.5mm intra-pair (HDMI 1.4 Sec 4.2.3)
- **RULE**: Inter-pair skew: <= 2mm length difference between any two TMDS pairs (HDMI 1.4 Sec 4.2.3)
- **RULE**: Place TPD12S016 within 10mm of HDMI connector (TPD12S016 DS Sec 11.1)

---

## DM3AT-SF-PEJM5

- **Function**: microSD push-push socket with card-detect switch
- **LCSC**: [C114218](https://www.lcsc.com/product-detail/C114218.html)
- **Footprint**: `Connector_Card:microSD_HiroseDM3AT-SF-PEJM5_Push-Push` (microSD push-push SMD)
- **Stock at LCSC**: 18,973
- **Unit price**: $1.4600
- **Datasheet**: [DM3 series, 2023](https://www.hirose.com/en/product/document?clcode=CL0540-1284-2-51&productname=DM3AT-SF-PEJM5(51)&series=DM3)
- **Reference design citation**: SD Spec Part 1, Sec 4.5 - SD Bus Topology
- **Instances on carrier**: 1

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `VDD` | `GND` | `4u7_0402_X5R` | 1 | SD Spec Part 1 Sec 6.3: VDD bulk cap (>= 4.7uF for card insertion transients) |
| `VDD` | `GND` | `100n_0402_X7R` | 1 | SD Spec: VDD HF bypass |
| `DAT0` | `VDD` | `10k_0402_1%` | 1 | SD Spec Sec 6.5: DAT0 pull-up 10-100k |
| `DAT1` | `VDD` | `10k_0402_1%` | 1 | SD Spec Sec 6.5: DAT1 pull-up 10-100k |
| `DAT2` | `VDD` | `10k_0402_1%` | 1 | SD Spec Sec 6.5: DAT2 pull-up 10-100k |
| `DAT3_CD` | `VDD` | `10k_0402_1%` | 1 | SD Spec Sec 6.5: DAT3/CD pull-up |
| `CMD` | `VDD` | `10k_0402_1%` | 1 | SD Spec Sec 6.5: CMD pull-up 10-100k |
| `CD_SW` | `+3V3` | `10k_0402_1%` | 1 | Card-detect to host GPIO via pull-up + switch to GND |

### Pins requiring no external components (per datasheet)

- `CLK`

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Route SDIO_CLK with matched length to SDIO_CMD and DAT[0..3] (length match within 5mm) (SD Spec Sec 6.5 - SDIO timing margin)
- info: Place series 22 ohm termination on each SDIO line near host SoM (already provided in SoM)

---

## RJHSE5380

- **Function**: Bare shielded RJ45 with 2 integrated LEDs, right-angle TH
- **LCSC**: [C464586](https://www.lcsc.com/product-detail/C464586.html)
- **Footprint**: `Connector_RJ:RJ45_Amphenol_RJHSE5380_Horizontal` (RJ45 TH right-angle)
- **Stock at LCSC**: 1,283
- **Unit price**: $0.9800
- **Datasheet**: [2023](https://www.amphenol-cs.com/product-series/rjhse5380.html)
- **Reference design citation**: Amphenol RJHSE5380 datasheet, pin diagram
- **Instances on carrier**: 1

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `LED1_A` | `+3V3` | `330R_0402_1%` | 1 | LED current limit: 3.3V - 2.2V Vf / 330R ~ 3mA (Green Link) |
| `LED2_A` | `+3V3` | `330R_0402_1%` | 1 | LED current limit: 3.3V - 2.0V Vf / 330R ~ 4mA (Yellow Activity) |

### Pins requiring no external components (per datasheet)

- `MDI0_N`
- `MDI0_P`
- `MDI1_N`
- `MDI1_P`
- `MDI2_N`
- `MDI2_P`
- `MDI3_N`
- `MDI3_P`

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Connect shield tabs (SH1..SH4) directly to CHASSIS_GND copper pour (EMI compliance)
- **RULE**: Keep RJ45 within 30mm of HX5008NLT magnetics; route MDI pairs as 100R differential (IEEE 802.3 / Pulse layout guide)

---

## Summary

- ICs with reference circuits: **17**
- Total IC instances on carrier: **27**
- Total external supporting parts (sum across all IC instances): **120**

Every supporting part on this carrier traces back to a specific section/figure of an IC datasheet. Review this document before PCB tape-out to validate design intent.
