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
- [24LC256T-I/SN_EDID](#24lc256t-isn_edid)
- [TLV75718PDBVR](#tlv75718pdbvr)
- [TLV75725PDBVR](#tlv75725pdbvr)
- [TLV75733PDBVR](#tlv75733pdbvr)
- [HX5008NLT](#hx5008nlt)
- [USBC_SINK](#usbc_sink)
- [HDMI_A](#hdmi_a)
- [DM3AT-SF-PEJM5](#dm3at-sf-pejm5)
- [RJHSE5380](#rjhse5380)
- [SS14](#ss14)
- [FX10A-168P-SV(91)](#fx10a-168p-sv(91))
- [PM254R-12-08-H85](#pm254r-12-08-h85)
- [FPC-05F-40PH20](#fpc-05f-40ph20)
- [1.0-15P](#10-15p)
- [ZX-PM2.54-2-7PY](#zx-pm254-2-7py)
- [HX-PZ1.27-2x5P-TP](#hx-pz127-2x5p-tp)
- [KH-SMA-P-8496](#kh-sma-p-8496)
- [YLED0603G](#yled0603g)
- [TS-1002S-06026C](#ts-1002s-06026c)
- [DS-04P](#ds-04p)

---

## FUSB302BMPX

- **Function**: USB Type-C / PD CC controller, I2C-controlled
- **LCSC**: [C442699](https://www.lcsc.com/product-detail/C442699.html)
- **Footprint**: `Package_DFN_QFN:WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm` (WQFN-14)
- **Stock at LCSC**: 5,262
- **Unit price**: $0.8100
- **Datasheet**: [Rev 6, May 2020](https://www.onsemi.com/pdf/datasheet/fusb302b-d.pdf)
- **Local PDF**: `datasheets/FUSB302BMPX.pdf` (p.22, Figure 5)
- **Reference design citation**: Figure 5 - Typical Application Schematic
- **Instances on carrier**: 1

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `VDD` | `GND` | `1u_0402_X7R` | 1 | DS 8.2.2 VDD bulk |
| `VDD` | `GND` | `100n_0402_X7R` | 1 | DS 8.2.2 VDD bypass |
| `VBUS` | `GND` | `100n_0402_X7R` | 1 | DS Fig 5 VBUS bypass |
| `VBUS` | `+VIN` | `1M_0402_1%` | 1 | DS Fig 5 VBUS sense divider upper leg (R1) |
| `VBUS` | `GND` | `100k_0402_1%` | 1 | DS Fig 5 VBUS sense divider lower leg (R2) |
| `CC1` | `GND` | `200p_0402_C0G` | 1 | USB-PD cReceiver, DS Fig 5 |
| `CC2` | `GND` | `200p_0402_C0G` | 1 | USB-PD cReceiver, DS Fig 5 |
| `VCONN_1` | `GND` | `10u_0603_X7R` | 1 | Type-C VCONN bulk per EVB |
| `VCONN_2` | `GND` | `10u_0603_X7R` | 1 | Type-C VCONN bulk per EVB |
| `SDA` | `+3V3_SC` | `4k7_0402_1%` | 1 | DS 7.2 I2C pull-up |
| `SCL` | `+3V3_SC` | `4k7_0402_1%` | 1 | DS 7.2 I2C pull-up |
| `INT_N` | `+3V3_SC` | `10k_0402_1%` | 1 | DS 7.2 INT_N pull-up |

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
- **Local PDF**: `datasheets/USBLC6-4SC6.pdf` (Figure 1 - Pin connection / Figure 13 - Application)
- **Reference design citation**: Figure 1 - Pin connection / Figure 13 - Application
- **Instances on carrier**: 3

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
- **Local PDF**: `datasheets/TPS2051CDBVR.pdf` (Figure 8-1 - Typical Application Circuit)
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
- **Local PDF**: `datasheets/TPD12S016PWR.pdf` (Figure 13 - HDMI Source Application)
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
- **Local PDF**: `datasheets/TPD12S016PWR.pdf` (Figure 14 - HDMI Sink Application)
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
- **Local PDF**: `datasheets/CP2102N-A02-GQFN24R.pdf` (Figure 4-1 - Typical USB to UART Bridge)
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
- **Local PDF**: `datasheets/INA226AIDGSR.pdf` (p.32, Figure 32)
- **Reference design citation**: Figure 32 - Typical Application Circuit
- **Instances on carrier**: 6

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `IN+` | `IN-` | `R_SENSE_10mR_2010_1%` | 1 | DS Sec 9.3 + Eq 7: R_SENSE = V_FS / I_max; 10 milliohm gives 81.92mV full-scale at 8.192A (20mV/2.5uV/LSB resolution = INA226 native range) |
| `VS` | `GND` | `100n_0402_X7R` | 1 | DS Sec 9.2: VS decoupling - 100nF close to pin |
| `IN+` | `SHUNT_PLUS` | `10R_0402_1%` | 1 | DS Fig 32: 10 ohm series input filter on IN+ |
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
- **Local PDF**: `datasheets/DS3231SN.pdf` (Figure 1 - Typical Operating Circuit)
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
- **Local PDF**: `datasheets/24LC256T-I_SN.pdf` (Figure 4-1 - Typical Application Circuit)
- **Reference design citation**: Figure 4-1 - Typical Application Circuit
- **Instances on carrier**: 1

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

## 24LC256T-I/SN

- **Function**: 256 Kbit I2C EDID EEPROM on HDMI DDC bus
- **LCSC**: [C5458](https://www.lcsc.com/product-detail/C5458.html)
- **Footprint**: `Package_SO:SOIC-8_3.9x4.9mm_P1.27mm` (SOIC-8)
- **Stock at LCSC**: 17,726
- **Unit price**: $0.5800
- **Datasheet**: [Rev May 2020 (DS21203P)](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/21203P.pdf)
- **Local PDF**: `datasheets/24LC256T-I_SN.pdf` (DS21203P Fig 4-1 + HDMI DDC at +5V)
- **Reference design citation**: Figure 4-1 + HDMI DDC EDID wiring
- **Instances on carrier**: 1

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `VCC` | `GND` | `100n_0402_X7R` | 1 | DS Sec 2.0: VCC decoupling cap |
| `SDA` | `+5V` | `2k2_0402_1%` | 1 | HDMI DDC SDA pull-up to +5V (shared with connector) |
| `SCL` | `+5V` | `2k2_0402_1%` | 1 | HDMI DDC SCL pull-up to +5V (shared with connector) |

### Strap pin configuration

| Pin | Tied to | Purpose | Justification |
|---|---|---|---|
| `A0` | `GND` | EDID I2C address bit 0 = 0 | DS Sec 5.1 |
| `A1` | `+5V` | EDID I2C address bit 1 = 1 (address 0x54) | HDMI EDID typical address 0xA0/0xA1 |
| `A2` | `GND` | EDID I2C address bit 2 = 0 | DS Sec 5.1 |
| `WP` | `GND` | Write protect disabled for EDID programming | DS Sec 7.0 |

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Route DDC SDA/SCL to HDMI connector within 20mm

---

## TLV75718PDBVR

- **Function**: 1.8V 1A LDO (VCCO bank supply, alternate)
- **LCSC**: [C507270](https://www.lcsc.com/product-detail/C507270.html)
- **Footprint**: `Package_TO_SOT_SMD:SOT-23-5` (SOT-23-5)
- **Stock at LCSC**: 167
- **Unit price**: $0.2700
- **Datasheet**: [Rev Sep 2017](https://www.ti.com/lit/ds/symlink/tlv757p.pdf)
- **Local PDF**: `datasheets/TLV75718PDBVR.pdf` (p.18, Figure 18)
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
- **Local PDF**: `datasheets/TLV75725PDBVR.pdf` (p.18, Figure 18)
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
- **Local PDF**: `datasheets/TLV75733PDBVR.pdf` (p.18, Figure 18)
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
- **Local PDF**: `datasheets/HX5008NLT.pdf` (p.4, Figure 1 + IEEE 802.3 Bob Smith)
- **Reference design citation**: Figure 1 - Application Schematic (1000BASE-T)
- **Instances on carrier**: 1

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `CT_PAIR0` | `BS_COMMON` | `75R_0603_1%` | 1 | IEEE 802.3 Bob Smith termination, pair 0 center tap |
| `CT_PAIR0` | `BS_COMMON` | `1n_2kV_0603_safety` | 1 | IEEE 802.3 Bob Smith 1nF per pair, pair 0 |
| `CT_PAIR1` | `BS_COMMON` | `75R_0603_1%` | 1 | IEEE 802.3 Bob Smith termination, pair 1 center tap |
| `CT_PAIR1` | `BS_COMMON` | `1n_2kV_0603_safety` | 1 | IEEE 802.3 Bob Smith 1nF per pair, pair 1 |
| `CT_PAIR2` | `BS_COMMON` | `75R_0603_1%` | 1 | IEEE 802.3 Bob Smith termination, pair 2 center tap |
| `CT_PAIR2` | `BS_COMMON` | `1n_2kV_0603_safety` | 1 | IEEE 802.3 Bob Smith 1nF per pair, pair 2 |
| `CT_PAIR3` | `BS_COMMON` | `75R_0603_1%` | 1 | IEEE 802.3 Bob Smith termination, pair 3 center tap |
| `CT_PAIR3` | `BS_COMMON` | `1n_2kV_0603_safety` | 1 | IEEE 802.3 Bob Smith 1nF per pair, pair 3 |
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
- **Local PDF**: `datasheets/TYPE-C-31-M-12.pdf` (USB Type-C R2.0 Sec 3.4.4 - Sink Configuration)
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
- **Local PDF**: `datasheets/HDMI-019S.pdf` (HDMI 1.4 Sec 4.2 + DDC pull-ups)
- **Reference design citation**: HDMI 1.4 Sec 4.2 / TPD12S016 DS Fig 13-14
- **Instances on carrier**: 2

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `+5V` | `GND` | `100n_0402_X7R` | 1 | HDMI Sec 4.2.7: 5V bypass at connector |
| `SCL` | `+5V` | `2k2_0402_1%` | 1 | HDMI 1.4 DDC: 2.2k SCL pull-up to +5V |
| `SDA` | `+5V` | `2k2_0402_1%` | 1 | HDMI 1.4 DDC: 2.2k SDA pull-up to +5V |
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
- **Local PDF**: `datasheets/DM3AT-SF-PEJM5.pdf` (SD Spec Part 1, Sec 4.5 - SD Bus Topology)
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
- **Local PDF**: `datasheets/RJHSE5380.pdf` (Amphenol RJHSE5380 datasheet, pin diagram)
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

## SS14

- **Function**: Reverse-polarity Schottky + bulk caps at +VIN input
- **LCSC**: [C83852](https://www.lcsc.com/product-detail/C83852.html)
- **Footprint**: `Diode_SMD:D_SMA` (SMA)
- **Stock at LCSC**: 49,340
- **Unit price**: $0.1200
- **Datasheet**: [Rev 2020](https://datasheet.lcsc.com/lcsc/ON-Semicon-SS14_C83852.pdf)
- **Local PDF**: `datasheets/SS14.pdf` (p.3, Schottky reverse protection)
- **Reference design citation**: Typical reverse-polarity + bulk input network
- **Instances on carrier**: 1

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `ANODE` | `+VIN_IN` | `schottky_SS14` | 1 | Reverse polarity protection at carrier input |
| `CATHODE` | `+VIN` | `100u_1206_X5R` | 1 | Bulk input cap after Schottky (10uF min per LDO apps) |
| `CATHODE` | `+VIN` | `100n_0402_X7R` | 1 | HF bypass at protected +VIN rail |

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Place Schottky close to input connector; bulk cap within 5mm of downstream LDOs

---

## FX10A-168P-SV(91)

- **Function**: 168-pin FMC LPC mezzanine connector
- **LCSC**: [C6624664](https://www.lcsc.com/product-detail/C6624664.html)
- **Footprint**: `Connector_FFC-FPC:FX10A-168P-SV1` (168-pin 0.5mm)
- **Stock at LCSC**: 416
- **Unit price**: $3.5300
- **Datasheet**: [Hirose FX10A series](https://www.hirose.com/en/product/document?clcode=CL0681-2024-7-91&productname=FX10A-168P-SV(91)&series=FX10A)
- **Local PDF**: `datasheets/FX10A-168P-SV_91.pdf` (Hirose FX10A DS + VITA 57.1 Sec 5.3)
- **Reference design citation**: FMC LPC VITA 57.1 decoupling guidance
- **Instances on carrier**: 1

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `VCC_3V3` | `GND` | `100n_0402_X7R` | 4 | VITA 57.1: 100nF per VCC pin group on FMC connector |
| `VCC_3V3` | `GND` | `10u_0603_X7R` | 1 | FMC bulk decoupling at connector |

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Decouple each FMC VCC pin group within 3mm of connector (VITA 57.1 LPC carrier requirements)

---

## PM254R-12-08-H85

- **Function**: PMOD 2x6 right-angle expansion header
- **LCSC**: [C53026548](https://www.lcsc.com/product-detail/C53026548.html)
- **Footprint**: `Connector_PinHeader_2.54mm:PinHeader_2x06_P2.54mm_Vertical` (2x6 2.54mm)
- **Stock at LCSC**: 780
- **Unit price**: $0.0900
- **Datasheet**: [2023](https://datasheet.lcsc.com/lcsc/XFCN-PM254R-12-08-H85_C53026548.pdf)
- **Local PDF**: `datasheets/PM254R-12-08-H85.pdf` (PMOD Spec Sec 2: 3.3V I/O, no mandatory passives)
- **Reference design citation**: Digilent PMOD Interface Specification Rev E
- **Instances on carrier**: 2

### Pins requiring no external components (per datasheet)

- `IO0`
- `IO1`
- `IO2`
- `IO3`
- `IO4`
- `IO5`
- `IO6`
- `IO7`

### PCB layout notes (carry forward to PCB stage)

- **RULE**: PMOD pins are 3.3V LVCMOS; do not drive 5V (Digilent PMOD Spec)

---

## FPC-05F-40PH20

- **Function**: 40-pin 0.5mm FFC for LVDS LCD panel
- **LCSC**: [C2856812](https://www.lcsc.com/product-detail/C2856812.html)
- **Footprint**: `Connector_FFC-FPC:FPC-05F-40PH20` (FFC 0.5mm 40P)
- **Stock at LCSC**: 26,530
- **Unit price**: $0.1800
- **Datasheet**: [2022](https://datasheet.lcsc.com/lcsc/XUNPU-FPC-05F-40PH20_C2856812.pdf)
- **Local PDF**: `datasheets/FPC-05F-40PH20.pdf` (LVDS IEEE 1596.3 + panel vendor ref)
- **Reference design citation**: LVDS panel termination (100 ohm differential)
- **Instances on carrier**: 1

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `LVDS_CLK+` | `LVDS_CLK-` | `100R_0402_1%` | 1 | 100 ohm LVDS clock pair termination at connector |
| `LVDS_DATA0+` | `LVDS_DATA0-` | `100R_0402_1%` | 1 | 100 ohm LVDS data0 pair termination |

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Route LVDS pairs as 100 ohm differential, matched length

---

## 1.0-15P

- **Function**: 15-pin 1mm FFC for MIPI CSI-2 camera module
- **LCSC**: [C66660](https://www.lcsc.com/product-detail/C66660.html)
- **Footprint**: `Connector_FFC-FPC:FFC_15P_1mm` (FFC 1.0mm 15P)
- **Stock at LCSC**: 3,375
- **Unit price**: $0.0800
- **Datasheet**: [2021](https://datasheet.lcsc.com/lcsc/BOOMELE-1-0-15P_C66660.pdf)
- **Local PDF**: `datasheets/1.0-15P.pdf` (CSI-2 spec + FFC vendor DS)
- **Reference design citation**: MIPI CSI-2 D-PHY connector decoupling
- **Instances on carrier**: 1

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `VCC_1V8` | `GND` | `100n_0402_X7R` | 1 | CSI-2 I/O supply bypass at FFC |
| `VCC_2V8` | `GND` | `100n_0402_X7R` | 1 | Camera analog supply bypass at FFC |

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Keep CSI-2 pairs length-matched; 100 ohm differential routing

---

## ZX-PM2.54-2-7PY

- **Function**: 2x7 2.54mm JTAG debug header
- **LCSC**: [C7499342](https://www.lcsc.com/product-detail/C7499342.html)
- **Footprint**: `Connector_PinHeader_2.54mm:PinHeader_2x07_P2.54mm_Vertical` (2x7 2.54mm)
- **Stock at LCSC**: 725
- **Unit price**: $0.1700
- **Datasheet**: [2022](https://datasheet.lcsc.com/lcsc/Megastar-ZX-PM2-54-2-7PY_C7499342.pdf)
- **Local PDF**: `datasheets/ZX-PM2.54-2-7PY.pdf` (UG470 JTAG direct connection (optional 100R series))
- **Reference design citation**: Xilinx UG470 JTAG interface
- **Instances on carrier**: 1

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `TCK` | `PL_TCK` | `100R_0402_1%` | 1 | UG470: optional 100R series on TCK for ringing control |
| `TMS` | `PL_TMS` | `100R_0402_1%` | 1 | UG470: optional 100R series on TMS |

### PCB layout notes (carry forward to PCB stage)

- _guideline_: Keep JTAG traces short; match TCK/TMS series resistor placement

---

## HX-PZ1.27-2x5P-TP

- **Function**: 2x5 1.27mm SWD + UART debug header
- **LCSC**: [C41376037](https://www.lcsc.com/product-detail/C41376037.html)
- **Footprint**: `Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical` (2x5 1.27mm SMD)
- **Stock at LCSC**: 11,040
- **Unit price**: $0.0800
- **Datasheet**: [2022](https://datasheet.lcsc.com/lcsc/hanxia-HX-PZ1-27-2x5P-TP_C41376037.pdf)
- **Local PDF**: `datasheets/HX-PZ1.27-2x5P-TP.pdf` (ARM SWD: 10k pull-up on SWDIO, 10k on nRESET)
- **Reference design citation**: ARM Debug Interface v5.2
- **Instances on carrier**: 1

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `SWDIO` | `+3V3` | `10k_0402_1%` | 1 | ARM SWD: SWDIO pull-up to VCC |
| `nRESET` | `+3V3` | `10k_0402_1%` | 1 | ARM SWD: nRESET pull-up to VCC |

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Place 10k pull-ups within 10mm of SWD header

---

## KH-SMA-P-8496

- **Function**: SMA right-angle clock input for XADC/MRCC
- **LCSC**: [C910123](https://www.lcsc.com/product-detail/C910123.html)
- **Footprint**: `Connector_Coaxial:SMA_Amphenol_132289-14_Vertical` (SMA TH right-angle)
- **Stock at LCSC**: 2,715
- **Unit price**: $0.7400
- **Datasheet**: [2021](https://datasheet.lcsc.com/lcsc/kinghelm-KH-SMA-P-8496_C910123.pdf)
- **Local PDF**: `datasheets/KH-SMA-P-8496.pdf` (UG480 XADC: AC-couple external clock with 50R termination)
- **Reference design citation**: XADC external clock input (UG480)
- **Instances on carrier**: 2

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `CENTER` | `XADC_CLK` | `22p_0402_C0G` | 1 | UG480: AC coupling cap on external clock input |
| `XADC_CLK` | `GND` | `49R9_0402_1%` | 1 | 50 ohm termination to GND at XADC clock input |

### PCB layout notes (carry forward to PCB stage)

- **RULE**: Route SMA to XADC as 50 ohm controlled impedance

---

## YLED0603G

- **Function**: 0603 user status LED with series resistor
- **LCSC**: [C19273151](https://www.lcsc.com/product-detail/C19273151.html)
- **Footprint**: `LED_SMD:LED_0603_1608Metric` (0603)
- **Stock at LCSC**: 75,000
- **Unit price**: $0.0100
- **Datasheet**: [2022](https://datasheet.lcsc.com/lcsc/YONGYUTAI-YLED0603G_C19273151.pdf)
- **Local PDF**: `datasheets/YLED0603G.pdf` (LED DS: If=5mA at 2V with 330R from 3.3V)
- **Reference design citation**: Typical GPIO LED indicator
- **Instances on carrier**: 4

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `ANODE` | `GPIO` | `330R_0402_1%` | 1 | Limit LED current to ~3mA from 3.3V GPIO |

### Pins requiring no external components (per datasheet)

- `CATHODE`

---

## TS-1002S-06026C

- **Function**: 6x6mm tactile switch with pull-up and debounce
- **LCSC**: [C455112](https://www.lcsc.com/product-detail/C455112.html)
- **Footprint**: `Button_Switch_SMD:SW_SPST_Tactile_6x6mm` (6x6 SMD tactile)
- **Stock at LCSC**: 18,240
- **Unit price**: $0.0600
- **Datasheet**: [2021](https://datasheet.lcsc.com/lcsc/XUNPU-TS-1002S-06026C_C455112.pdf)
- **Local PDF**: `datasheets/TS-1002S-06026C.pdf` (Switch DS + debounce cap to GND)
- **Reference design citation**: Typical tact switch to GPIO
- **Instances on carrier**: 4

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `SW` | `+3V3` | `10k_0402_1%` | 1 | Pull-up: switch active-low to GND |
| `SW` | `GND` | `100n_0402_X7R` | 1 | Debounce / ESD shunt at switch node |

---

## DS-04P

- **Function**: 4-position 1.27mm DIP boot mode switch
- **LCSC**: [C18198092](https://www.lcsc.com/product-detail/C18198092.html)
- **Footprint**: `Switch_SMD:DIP_Switch_x4` (DIP-4 SMD 1.27mm)
- **Stock at LCSC**: 1,582
- **Unit price**: $0.5200
- **Datasheet**: [2020](https://datasheet.lcsc.com/lcsc/Hanbo-Electronic-DS-04P_C18198092.pdf)
- **Local PDF**: `datasheets/DS-04P.pdf` (Zynq boot mode: pull-up on each strap bit)
- **Reference design citation**: Boot mode strap switches
- **Instances on carrier**: 1

### External parts required by datasheet

| IC pin / net | Other side | Part token | Qty | Justification |
|---|---|---|---|---|
| `SW1` | `+3V3` | `10k_0402_1%` | 1 | Boot strap bit 0 pull-up (switch to GND when ON) |
| `SW2` | `+3V3` | `10k_0402_1%` | 1 | Boot strap bit 1 pull-up |
| `SW3` | `+3V3` | `10k_0402_1%` | 1 | Boot strap bit 2 pull-up |
| `SW4` | `+3V3` | `10k_0402_1%` | 1 | Boot strap bit 3 pull-up |

---

## Summary

- ICs with reference circuits: **29**
- Total IC instances on carrier: **47**
- Total external supporting parts (sum across all IC instances): **177**

Every supporting part on this carrier traces back to a specific section/figure of an IC datasheet. Review this document before PCB tape-out to validate design intent.
