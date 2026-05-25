# Carrier Reference Circuits

Auto-generated design-intent record. For every IC on the carrier, this document shows the manufacturer reference circuit applied: every external part required by the datasheet, pin overrides, and layout notes. The EE reviews this document before PCB tape-out to confirm the carrier design follows each IC's reference design.

## Contents

- [U1 — TLV75733PDBVR](#u1-tlv75733pdbvr)
- [U2 — TLV75725PDBVR](#u2-tlv75725pdbvr)
- [U3 — TLV75718PDBVR](#u3-tlv75718pdbvr)
- [U1 — FUSB302BMPX](#u1-fusb302bmpx)
- [U2 — USBLC6-4SC6](#u2-usblc6-4sc6)

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
