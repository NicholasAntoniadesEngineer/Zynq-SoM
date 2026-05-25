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
**Datasheet:** [TLV75733PDBVR](https://www.ti.com/lit/ds/symlink/tlv757p.pdf) (Figure 7-4 - TLV757P Typical Application, p.19, Figure 7-4)  
**Footprint:** Package_TO_SOT_SMD:SOT-23-5  
**Supply rail:** +VIN  
**Min-circuit verified:** yes  

3.3V 1A LDO (main +3V3 carrier rail, SOT-23-5)

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| IN | GND | 1u_0402_X7R | 1 | DS Sec 7.1.1 + Fig 7-4: 1 uF ceramic input cap close to pin 1 |
| OUT | GND | 1u_0402_X7R | 1 | DS Sec 7.1.1 + Fig 7-4: 1 uF ceramic output cap (>= 0.47 uF effective for stability) |
| OUT | GND | 100n_0402_X7R | 1 | Additional HF bypass on output for transient response (complements 1 uF bulk) |
| EN | IN | 100k_0402_1% | 1 | DS Sec 6.4.1: EN pull-up to IN for always-on (V_EN >= V_HI = 1V); replace with GPIO for sequencing |

### Pin overrides

_None._

### No external required

_Pins explicitly left bare:_ NC

### Layout notes

- Place 1 uF input and 1 uF output caps within 5 mm of pins 1 (IN) and 5 (OUT) respectively for 3.3V stability (rule) — _DS Sec 7.4.1 Layout Guidelines_
- Use a copper ground plane under the LDO and add thermal vias around the device to distribute heat (P_D = (V_IN - V_OUT) * I_OUT) (guideline) — _DS Sec 7.4.1 + Sec 7.1.5 Power Dissipation_
- Keep IN trace short and low-impedance; if the input source is more than a few inches away, add additional bulk input capacitance in parallel with the 1 uF ceramic (guideline) — _DS Sec 7.3 Power Supply Recommendations_

## U2 — TLV75725PDBVR

**Block:** power  
**Datasheet:** [TLV75725PDBVR](https://www.ti.com/lit/ds/symlink/tlv757p.pdf) (Figure 7-4 - TLV757P Typical Application, p.19, Figure 7-4)  
**Footprint:** Package_TO_SOT_SMD:SOT-23-5  
**Supply rail:** +VIN  
**Min-circuit verified:** yes  

2.5V 1A LDO (SSTL/DCI reference supply, SOT-23-5)

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| IN | GND | 1u_0402_X7R | 1 | DS Sec 7.1.1 + Fig 7-4: 1 uF ceramic input cap close to pin 1 |
| OUT | GND | 1u_0402_X7R | 1 | DS Sec 7.1.1 + Fig 7-4: 1 uF ceramic output cap (>= 0.47 uF effective for stability) |
| OUT | GND | 100n_0402_X7R | 1 | Additional HF bypass on output for transient response (complements 1 uF bulk) |
| EN | IN | 100k_0402_1% | 1 | DS Sec 6.4.1: EN pull-up to IN for always-on (V_EN >= V_HI = 1V); replace with GPIO for sequencing |

### Pin overrides

_None._

### No external required

_Pins explicitly left bare:_ NC

### Layout notes

- Place 1 uF input and 1 uF output caps within 5 mm of pins 1 (IN) and 5 (OUT) respectively for 2.5V stability (rule) — _DS Sec 7.4.1 Layout Guidelines_
- Use a copper ground plane under the LDO and add thermal vias around the device to distribute heat (P_D = (V_IN - V_OUT) * I_OUT) (guideline) — _DS Sec 7.4.1 + Sec 7.1.5 Power Dissipation_
- Keep IN trace short and low-impedance; if the input source is more than a few inches away, add additional bulk input capacitance in parallel with the 1 uF ceramic (guideline) — _DS Sec 7.3 Power Supply Recommendations_

## U3 — TLV75718PDBVR

**Block:** power  
**Datasheet:** [TLV75718PDBVR](https://www.ti.com/lit/ds/symlink/tlv757p.pdf) (Figure 7-4 - TLV757P Typical Application, p.19, Figure 7-4)  
**Footprint:** Package_TO_SOT_SMD:SOT-23-5  
**Supply rail:** +VIN  
**Min-circuit verified:** yes  

1.8V 1A LDO (FPGA 1.8V bank supply, SOT-23-5)

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| IN | GND | 1u_0402_X7R | 1 | DS Sec 7.1.1 + Fig 7-4: 1 uF ceramic input cap close to pin 1 |
| OUT | GND | 1u_0402_X7R | 1 | DS Sec 7.1.1 + Fig 7-4: 1 uF ceramic output cap (>= 0.47 uF effective for stability) |
| OUT | GND | 100n_0402_X7R | 1 | Additional HF bypass on output for transient response (complements 1 uF bulk) |
| EN | IN | 100k_0402_1% | 1 | DS Sec 6.4.1: EN pull-up to IN for always-on (V_EN >= V_HI = 1V); replace with GPIO for sequencing |

### Pin overrides

_None._

### No external required

_Pins explicitly left bare:_ NC

### Layout notes

- Place 1 uF input and 1 uF output caps within 5 mm of pins 1 (IN) and 5 (OUT) respectively for 1.8V stability (rule) — _DS Sec 7.4.1 Layout Guidelines_
- Use a copper ground plane under the LDO and add thermal vias around the device to distribute heat (P_D = (V_IN - V_OUT) * I_OUT) (guideline) — _DS Sec 7.4.1 + Sec 7.1.5 Power Dissipation_
- Keep IN trace short and low-impedance; if the input source is more than a few inches away, add additional bulk input capacitance in parallel with the 1 uF ceramic (guideline) — _DS Sec 7.3 Power Supply Recommendations_

## U1 — INA226AIDGSR

**Block:** power_mon  
**Datasheet:** [INA226AIDGSR](https://www.ti.com/lit/ds/symlink/ina226.pdf) (Figure 8-1 - Typical Circuit Configuration, p.28, Figure 8-1)  
**Footprint:** Package_SO:VSSOP-10_3x3mm_P0.5mm  
**Supply rail:** +3V3  
**Min-circuit verified:** yes  

Bidirectional I2C current/voltage/power monitor, 16-bit, 36 V common-mode, VSSOP-10

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| Vin+ | Vin- | R_SENSE_10mR_2010_1% | 1 | DS Sec 6.5 + Eq 7: R_SENSE = V_FS / I_max. 10 mOhm gives 81.92 mV full-scale at 8.192 A (matches the 16-bit / 2.5 uV LSB native range); standardised across all 6 carrier instances |
| VS | GND | 100n_0402_X7R | 1 | DS Sec 8.3 + Fig 8-1: 0.1 uF C_BYPASS on VS as close as possible to the device |
| SDA | +3V3 | 4k7_0402_1% | 1 | DS Fig 8-1 + Sec 8.2.1.2: I2C SDA pull-up to bus supply |
| SCL | +3V3 | 4k7_0402_1% | 1 | DS Fig 8-1 + Sec 8.2.1.2: I2C SCL pull-up to bus supply |
| ~{Alert} | +3V3 | 4k7_0402_1% | 1 | DS Sec 8.2.1.2 + Fig 8-1: ALERT open-drain pull-up to V_VS |

### Pin overrides

| Pin | Net |
|---|---|
| Vbus | +VIN |

### Layout notes

- Kelvin-connect IN+ and IN- to the shunt resistor pads (4-wire or true Kelvin geometry). Route the sense traces away from the high-current shunt-to-load and shunt-to-source paths (rule) — _DS Sec 8.4.1 Layout Guidelines_
- Place the 0.1 uF VS bypass cap as close as possible to the VS (pin 6) and GND (pin 7) pins of the device (rule) — _DS Sec 8.3 Power Supply Recommendations + Fig 8-4_
- Route Vin+ / Vin- as a tight differential pair from the shunt back to pins 9/10 to reject common-mode noise on long sense traces (guideline) — _DS Sec 8.4.1 Layout Guidelines_
- Connect the Vbus pin (8) directly to the monitored power rail via a via to the power plane; the bus voltage measurement is independent of V_S, so noisy or switching rails can be sensed without affecting the device supply — _DS Fig 8-4 note (1)_

## U1 — FUSB302BMPX

**Block:** usb_pd  
**Datasheet:** [FUSB302BMPX](https://www.onsemi.com/pdf/datasheet/fusb302b-d.pdf) (Figure 18 - Reference Schematic Diagram, p.30, Figure 18 + Table 43)  
**Footprint:** Package_DFN_QFN:WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm  
**Supply rail:** +3V3  
**Min-circuit verified:** yes  

USB Type-C / PD CC controller, I2C-controlled, WQFN-14

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| VDD | GND | 1u_0402_X7R | 1 | DS Table 43 C_VDD2: 1uF VDD bulk |
| VDD | GND | 100n_0402_X7R | 1 | DS Table 43 C_VDD1: 100nF VDD HF bypass |
| VBUS | GND | 100n_0402_X7R | 1 | DS Fig 18: VBUS pin bypass (HF noise filter) |
| VBUS | +VIN | 1M_0402_1% | 1 | Carrier VBUS sense divider upper leg (1M, R1) |
| VBUS | GND | 100k_0402_1% | 1 | Carrier VBUS sense divider lower leg (100k, R2) |
| CC1 | GND | 200p_0402_C0G | 1 | DS Table 43 C_RECV: 200pF on CC1 (min of 200-600pF) |
| CC2 | GND | 200p_0402_C0G | 1 | DS Table 43 C_RECV: 200pF on CC2 (min of 200-600pF) |
| VCONN_1 | GND | 10u_0603_X7R | 1 | DS Table 43 C_BULK: 10uF VCONN bulk (min 10uF) |
| VCONN_1 | GND | 100n_0402_X7R | 1 | DS Table 43 C_VCONN: 100nF VCONN HF bypass |
| VCONN_2 | GND | 10u_0603_X7R | 1 | DS Table 43 C_BULK: 10uF VCONN bulk (paralleled pad) |
| VCONN_2 | GND | 100n_0402_X7R | 1 | DS Table 43 C_VCONN: 100nF VCONN HF bypass (paralleled pad) |
| SDA | +3V3_SC | 4k7_0402_1% | 1 | DS Table 43 R_PU: 4.7k I2C SDA pull-up (1.71V-VDD range) |
| SCL | +3V3_SC | 4k7_0402_1% | 1 | DS Table 43 R_PU: 4.7k I2C SCL pull-up |
| INT_N | +3V3_SC | 4k7_0402_1% | 1 | DS Table 43 R_PU_INT: 4.7k INT_N pull-up (open-drain) |

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

- VDD decoupling: place 100nF (C_VDD1) within 1mm of VDD pin, 1uF (C_VDD2) within 3mm. Return current through shortest GND via (rule) — _DS Table 43 + general decoupling practice_
- CC1/CC2 traces: 90 ohm differential impedance to USB-C connector, matched length within 5mm. Place C_RECV (200pF) next to FUSB302, not next to the USB-C connector (USB-PD reference uses C_RECV as the receiver filter cap) (rule) — _USB-C R2.0 Sec 3.2.1 + DS Fig 18 (C_RECV at FUSB302 side)_
- VBUS trace from USB-C VBUS to FUSB302 pin 2: keep under 10mm, route as a wide trace (>= 0.3mm) to minimise series inductance for the VBUS sense comparator (vBC_LVL trip thresholds <= 1.31V) (guideline) — _DS Table 10 (vBC_LVL) + VBUS sense latency_
- Connect the exposed pad (EP, pin 15 / GND_EP) to the PCB GND plane with a 3x3 via stitch for thermal + electrical performance (rule) — _DS Fig 5 mechanical drawing (EP=Connect to GND for Thermal)_
- I2C pull-ups (4.7k) tie to the same +3V3_SC rail as the STM32 I2C controller; DS Table 13 note 6 requires VPU between 1.71V and VDD (rule) — _DS Table 13 note 6 (I2C pull-up voltage 1.71V-VDD)_

## U2 — USBLC6-4SC6

**Block:** usb_pd  
**Datasheet:** [USBLC6-4SC6](https://www.st.com/resource/en/datasheet/usblc6-4.pdf) (Figure 14 - USB 2.0 port application; Figure 18 - PCB layout, p.8 Fig 14 (application) + p.9 Fig 18 (layout / C_BUS))  
**Footprint:** Package_TO_SOT_SMD:SOT-23-6  
**Min-circuit verified:** yes  

USB 2.0 / 480 Mb/s ESD protection, 4 lines, SOT-23-6L

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| VBUS | GND | 100n_0402_X7R | 1 | DS Fig 18 C_BUS: 100nF V_BUS decoupling (PCB layout) |

### Pin overrides

| Pin | Net |
|---|---|
| I/O1 | USB_DP |
| I/O2 | USB_DM |

### No external required

_Pins explicitly left bare:_ I/O1, I/O2, I/O3, I/O4

### Layout notes

- Place USBLC6 within 5mm of the USB connector on the data-line side -- the ESD protection MUST sit between the connector and the device being protected (DS Sec 2.3: 'put the protection device as close as possible to the disturbance source') (rule) — _DS Sec 2.3 / Fig 7 (optimised layout) + Fig 8_
- Route USB D+/D- THROUGH the USBLC6 pads (tee-stub branch is unacceptable). The data line enters on one side of the SOT-23-6 and exits on the other; do not place the device on a stub off the main pair (DS Sec 2.3 Fig 7 'unsuitable layout' vs 'optimised layout') (rule) — _DS Fig 7 (layout optimisation)_
- Maintain 90 ohm differential impedance through the USBLC6 footprint. Length-match D+/D- through the package (the 0.04 pF C(I/O-I/O) typ value keeps the imbalance under USB 2.0 spec) (rule) — _USB 2.0 Sec 7.1.6 + DS Table 2 (line capacitance)_
- Tie the GND pin (pin 2) directly to the PCB GND plane with the shortest possible trace -- the negative-going clamp current returns here, and L_GND.di/dt adds directly to the clamp voltage seen by the protected line (DS Sec 2.2) (rule) — _DS Sec 2.2 (overvoltage due to parasitic inductances)_
- Tie the V_BUS pin (pin 3) to the USB +5V (or +VIN) rail through the shortest possible trace; the positive clamp diodes shunt to V_BUS, so L_VBUS in series with C_BUS hurts response time. The 100nF C_BUS cap should be within 2mm of pin 3 (rule) — _DS Sec 2.2 + Fig 18_

## U1 — TPS2051CDBVR

**Block:** usbc_otg  
**Datasheet:** [TPS2051CDBVR](https://www.ti.com/lit/ds/symlink/tps2051c.pdf) (Figure 23 - Typical Application Schematic, p.17, Figure 23)  
**Footprint:** Package_TO_SOT_SMD:SOT-23-5  
**Supply rail:** +VIN  
**Min-circuit verified:** yes  

USB current-limited load switch, 0.5 A, active-high enable, SOT-23-5

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| IN | GND | 1u_0402_X7R | 1 | DS Sec 9.2.2.1 + Fig 23: 0.1 uF min on IN (we use 1 uF for transient/inrush headroom) |
| IN | GND | 100n_0402_X7R | 1 | DS Fig 23 + Sec 11 Layout: 0.1 uF ceramic close to IN/GND pins |
| OUT | GND | 100u_1206_X5R | 1 | DS Sec 9.2.2.1 + Fig 23: 120-150 uF for USB-2.0 VBUS; 100 uF 1206 carries the standard with derating |
| OUT | GND | 100n_0402_X7R | 1 | HF bypass on OUT for USB transient response (complements bulk cap) |
| ~{FLT} | +3V3 | 10k_0402_1% | 1 | DS Sec 8.3.5 + Fig 23: ~FLT is open-drain, 10k pull-up to logic supply |

### Pin overrides

| Pin | Net |
|---|---|
| EN | STM32_USBOTG_VBUS_EN |
| ~{FLT} | STM32_USBOTG_OC_N |

### Layout notes

- Place the 0.1 uF input bypass cap near the IN and GND pins with a low-inductance trace (rule) — _DS Sec 11.1 Layout Guidelines #1_
- Place the >= 10 uF output cap near the OUT and GND pins with a low-inductance trace (a 120-150 uF bulk is required for USB 2.0 VBUS standard compliance) (rule) — _DS Sec 11.1 Layout Guidelines #2 + USB 2.0 VBUS spec_
- Add copper pour around the device on both sides of the SOT-23-5 to spread heat (DS Sec 11.3: theta_JA depends strongly on PCB copper area at the 0.5 A rated current) (guideline) — _DS Sec 11.3 Power Dissipation and Junction Temperature_
- EN must not be left floating -- the input is driven directly from a STM32 GPIO. Keep the EN trace short to avoid noise coupling into the enable network at switch turn-on (rule) — _DS Sec 8.3.2 Enable: enable must not be left open_

## U1 — CP2102N-A02-GQFN24R

**Block:** uart_bridge  
**Datasheet:** [CP2102N-A02-GQFN24R](https://www.silabs.com/documents/public/data-sheets/cp2102n-datasheet.pdf) (Figure 2.1 (bus-powered, internal regulator) + Figure 2.5 (USB pins), p.5 Fig 2.1 + p.8 Fig 2.5 (bus-powered USB connection))  
**Footprint:** Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm  
**Supply rail:** +VIN  
**Min-circuit verified:** yes  

USB to UART bridge, USB 2.0 FS, internal 3.3V regulator + 48 MHz oscillator, QFN-24

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| VREGIN | GND | 4u7_0402_X5R | 1 | DS Fig 2.1: 4.7uF VREGIN bulk (5V regulator input) |
| VREGIN | GND | 100n_0402_X7R | 1 | DS Fig 2.1: 100nF VREGIN HF bypass |
| VDD | GND | 4u7_0402_X5R | 1 | DS Fig 2.1: 4.7uF VDD bulk (regulator output, 3.3V) |
| VDD | GND | 100n_0402_X7R | 1 | DS Fig 2.1: 100nF VDD HF bypass |
| VIO | GND | 100n_0402_X7R | 1 | DS Sec 2.1: 0.1uF bypass on every power pin (VIO=VDD) |
| VBUS | +VIN | 22k1_0402_1% | 1 | DS Sec 2.3 / Fig 2.5: 22.1k upper leg of VBUS sense divider |
| VBUS | GND | 47k5_0402_1% | 1 | DS Sec 2.3 / Fig 2.5: 47.5k lower leg of VBUS sense divider |
| ~{RST} | CP2102N_VDD33 | 1k_0402_1% | 1 | DS Sec 2.1: 1 kohm RSTb pull-up to VIO (recommended) |

### Pin overrides

| Pin | Net |
|---|---|
| VREGIN | +VIN |
| VDD | CP2102N_VDD33 |
| VIO | CP2102N_VDD33 |
| D+ | USB_UART_DP |
| D- | USB_UART_DM |
| TXD | ZYNQ_PS_UART0_RXD |
| RXD | ZYNQ_PS_UART0_TXD |
| ~{RTS} | ZYNQ_PS_UART0_CTS_N |
| ~{CTS} | ZYNQ_PS_UART0_RTS_N |

### No external required

_Pins explicitly left bare:_ D+, D-, NC, RS485/GPIO.2, RXD, SUSPEND, TXD, ~{DCD}, ~{DSR}, ~{DTR}, ~{RI}/CLK, ~{RXT}/GPIO.1, ~{SUSPEND}, ~{TXT}/GPIO.0, ~{WAKEUP}/GPIO.3

### Layout notes

- Each power pin (VREGIN pin 7, VDD pin 6, VIO pin 5) gets its OWN 4.7uF + 0.1uF bypass placed as close to the pin as possible. Do not share a single 4.7uF across VDD + VIO -- the DS caption is explicit: 'each power pin placed as close to the pins as possible' (rule) — _DS Sec 2.1 Fig 2.1 + Fig 2.2 figure captions_
- VBUS sense divider (22.1k/47.5k) is MANDATORY for bus-powered operation -- the VBUS pin abs-max is VIO+2.5V (DS Table 3.10) but USB cable VBUS reaches 5.25V. Divider scales it into spec while still meeting VIH=VIO-0.6V at low end. Do not omit (rule) — _DS Sec 2.3 + Table 3.10 (abs-max VBUS pin)_
- Connect exposed pad (EP, pin 25 / center) to GND plane with a 3x3 via stitch. EP is the chip's primary thermal path and the low-impedance GND return (rule) — _DS Sec 6.2 / 7.2 PCB Land Pattern notes_
- USB D+/D- routing: 90 ohm differential impedance to the USB-B (or USB-C) connector pads, length-matched within 2mm. Place USBLC6 ESD protection inline between the connector and the CP2102N D+/D- pins (if the parent block includes ESD) (rule) — _USB 2.0 Sec 7.1.6 + standard ESD-placement practice_
- RSTb pin (pin 9, ~RST in the symbol) is driven LOW during power-on and power-fail reset. 1 kohm pull-up to VIO holds it high otherwise. No external C is required -- DS Fig 2.1 shows only the pull-up — _DS Sec 2.1 (RSTb behaviour) + Fig 2.1 (no R-C filter)_
- No external crystal: the CP2102N integrates a 48 MHz oscillator (DS Table 3.5, +/- 0.7% over temp/supply). Do NOT add a crystal to the unused pins — _DS Sec 3.1.5 + Table 3.5 (Internal Oscillator)_

## U1 — TPD12S016PWR

**Block:** hdmi_tx  
**Datasheet:** [TPD12S016PWR](https://www.ti.com/lit/ds/symlink/tpd12s016.pdf) (Figure 15 - HDMI Source using one GPIO (CT_HPD), p.18 Figure 15 + p.21 Sec 10 layout)  
**Footprint:** Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm  
**Supply rail:** +3V3  
**Min-circuit verified:** yes  

HDMI source companion: 12-ch ESD + DDC/CEC/HPD level shifters + 5V load switch

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| VCCA | GND | 100n_0402_X7R | 1 | DS Fig 15: 100nF V_CCA decoupling close to pin 24 |
| VCCB | GND | 100n_0402_X7R | 1 | DS Fig 15: 100nF V_CC5V decoupling close to pin 11 |
| CT_CP_HPD | +3V3 | 10k_0402_1% | 1 | DS Sec 8.2.1 / Fig 15: CT_HPD = HIGH enables 5V load switch + HPD detection (active-high control input) |

### Pin overrides

| Pin | Net |
|---|---|
| VCCA | +3V3 |
| VCCB | +5V |

### No external required

_Pins explicitly left bare:_ CEC_A, CLK+, CLK-, D0+, D0-, D1+, D1-, D2+, D2-, HPD_A, HPD_B, SCL_A, SCL_B, SDA_A, SDA_B

### Layout notes

- Place TPD12S016 as close as possible to HDMI connector pin 1 (< 10mm) to minimise unprotected TMDS stub length (rule) — _DS Sec 10.1: ESD energy must dissipate at protection pins before reaching downstream traces_
- TMDS pairs: route as 100R differential, length-matched within 0.5mm intra-pair and <= 2mm inter-pair skew across all four pairs (rule) — _HDMI 1.4 Sec 4.2.3 + TPD12S016 DS Sec 7.3.4_
- Route TMDS lines straight (no 90-degree turns) and avoid vias between connector and TPD12S016 protection pins (rule) — _DS Sec 10.1: minimise EMI coupling and impedance discontinuity on the ESD path_
- Place the 100nF V_CCA and V_CC5V decoupling caps within 5mm of their respective supply pins (24 and 11) (rule) — _DS Sec 10.1: minimise impedance on the ESD return path_
- Provide a large ground via field under the device and tie all GND pins (6, 14, 19) to a continuous ground plane (rule) — _DS Sec 10.2: low-impedance GND is essential for ESD dissipation_

## U2 — 24LC256T-I/SN

**Block:** hdmi_tx  
**Datasheet:** [24LC256T-I/SN](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/21203P.pdf) (DS Sec 5.0 + HDMI 1.4 Sec 8.1.4 (EDID at 0xA0), p.8 Sec 5.0 Device Addressing + HDMI 1.4 EDID spec)  
**Footprint:** Package_SO:SOIC-8_3.9x4.9mm_P1.27mm  
**Supply rail:** +5V  
**Min-circuit verified:** yes  

256 Kbit I2C EDID EEPROM on HDMI DDC bus (5V, addr 0x50)

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| VCC | GND | 100n_0402_X7R | 1 | DS Sec 2.0: 100nF V_CC decoupling cap close to pin 8 |

### Pin overrides

_None._

### Strap pins

| Pin | Tied to | Purpose | Why |
|---|---|---|---|
| A0 | GND | A0 = 0 (mandatory for EDID I2C addr 0x50) | HDMI 1.4 Sec 8.1.4 / VESA E-DDC Sec 2.2.5 |
| A1 | GND | A1 = 0 | HDMI 1.4 Sec 8.1.4 / VESA E-DDC Sec 2.2.5 |
| A2 | GND | A2 = 0 (full EDID address = 0xA0/0xA1) | HDMI 1.4 Sec 8.1.4 / VESA E-DDC Sec 2.2.5 |
| WP | GND | Write protect disabled (Zynq PS programs EDID at first boot) | DS Sec 2.4: WP=GND -> writes enabled |

### No external required

_Pins explicitly left bare:_ SCL, SDA

### Layout notes

- Place EDID EEPROM on the HDMI cable side of TPD12S016, between TPD12S016 SDA_B / SCL_B and HDMI connector pins 15 / 16 (rule) — _HDMI 1.4 Sec 8.1 / TPD12S016 DS Fig 15_
- Route DDC SDA / SCL traces <= 20mm with V_CC bypass within 5mm of pin 8 to stay within HDMI 1.4 DDC capacitive-load budget (rule) — _HDMI 1.4 Sec 8.1.1 + DS Sec 2.0_
- EDID EEPROM V_CC must come from the same +5V node that supplies TPD12S016 5V_OUT (TX role) so DDC pull-ups and EEPROM share a single 5V reference (rule) — _HDMI 1.4 Sec 8.1.1 (DDC voltage level)_

## U1 — TPD12S016PWR

**Block:** hdmi_rx  
**Datasheet:** [TPD12S016PWR](https://www.ti.com/lit/ds/symlink/tpd12s016.pdf) (Figure 15 / Sec 7.3.8 (back-drive on V_CC5V in sink role), p.18 Figure 15 + p.15 Sec 7.3.8 back-drive protection)  
**Footprint:** Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm  
**Supply rail:** +3V3  
**Min-circuit verified:** yes  

HDMI sink companion: 12-ch ESD + DDC/CEC/HPD level shifters (5V sourced by upstream)

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| VCCA | GND | 100n_0402_X7R | 1 | DS Fig 15: 100nF V_CCA decoupling close to pin 24 |
| VCCB | GND | 100n_0402_X7R | 1 | DS Fig 15: 100nF V_CC5V decoupling close to pin 11 |
| CT_CP_HPD | +3V3 | 10k_0402_1% | 1 | DS Sec 8.2.1 / Fig 15: CT_HPD = HIGH enables 5V load switch + HPD detection (active-high control input) |

### Pin overrides

| Pin | Net |
|---|---|
| VCCA | +3V3 |
| VCCB | ZYNQ_HDMI_RX_5V_SENSE |

### No external required

_Pins explicitly left bare:_ CEC_A, CLK+, CLK-, D0+, D0-, D1+, D1-, D2+, D2-, HPD_A, HPD_B, SCL_A, SCL_B, SDA_A, SDA_B

### Layout notes

- Place TPD12S016 within 10mm of the HDMI receptacle to keep TMDS stubs short and the ESD path direct (rule) — _DS Sec 10.1_
- TMDS RX termination is handled internally by the Zynq HP I/O (50R to AVCC); do NOT add external termination on the cable side (rule) — _HDMI 1.4 Sec 4.2.5 + Zynq SelectIO TMDS_33 documentation_
- 5V_OUT pin (13) carries +5V SOURCED BY THE UPSTREAM transmitter; TPD12S016 back-drive protection (DS Sec 7.3.8) prevents reverse current into our 5V rail
- Tie all GND pins to a single low-impedance ground plane and place decoupling caps within 5mm of V_CCA (24) and V_CC5V (11) (rule) — _DS Sec 10.1_

## T1 — HX5008NLT

**Block:** ethernet  
**Datasheet:** [HX5008NLT](https://productfinder.pulseeng.com/files/datasheets/HX5008NL.pdf) (DS Sheet 2 SCHEMATIC + IEEE 802.3 Sec 40.7.1 Bob Smith network, Sheet 2 SCHEMATIC + ELECTRICAL CHARACTERISTICS)  
**Footprint:** Package_SO:SOIC-24W_7.5x15.4mm_P1.27mm  
**Min-circuit verified:** yes  

1000BASE-T 4-pair Ethernet magnetics module (1:1, 325uH, 1500V isolation)

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| CT_PAIR0 | BS_COMMON | 75R_0603_1% | 1 | IEEE 802.3 Sec 40.7.1 (Bob Smith): 75R from pair 0 line-side centre tap to common point |
| CT_PAIR0 | BS_COMMON | 1n_2kV_0603_safety | 1 | IEEE 802.3 Sec 40.7.1: 1nF/2kV (safety-rated) AC-couples pair 0 centre tap into the Bob Smith common node |
| CT_PAIR1 | BS_COMMON | 75R_0603_1% | 1 | IEEE 802.3 Sec 40.7.1 (Bob Smith): 75R from pair 1 line-side centre tap to common point |
| CT_PAIR1 | BS_COMMON | 1n_2kV_0603_safety | 1 | IEEE 802.3 Sec 40.7.1: 1nF/2kV (safety-rated) AC-couples pair 1 centre tap into the Bob Smith common node |
| CT_PAIR2 | BS_COMMON | 75R_0603_1% | 1 | IEEE 802.3 Sec 40.7.1 (Bob Smith): 75R from pair 2 line-side centre tap to common point |
| CT_PAIR2 | BS_COMMON | 1n_2kV_0603_safety | 1 | IEEE 802.3 Sec 40.7.1: 1nF/2kV (safety-rated) AC-couples pair 2 centre tap into the Bob Smith common node |
| CT_PAIR3 | BS_COMMON | 75R_0603_1% | 1 | IEEE 802.3 Sec 40.7.1 (Bob Smith): 75R from pair 3 line-side centre tap to common point |
| CT_PAIR3 | BS_COMMON | 1n_2kV_0603_safety | 1 | IEEE 802.3 Sec 40.7.1: 1nF/2kV (safety-rated) AC-couples pair 3 centre tap into the Bob Smith common node |
| BS_COMMON | CHASSIS_GND | 1n_2kV_0603_safety | 1 | IEEE 802.3 Sec 40.7.1 + EN 55032: 1nF/2kV safety cap AC-couples Bob Smith common to chassis GND for EMI return |

### Pin overrides

_None._

### No external required

_Pins explicitly left bare:_ MDI0_N, MDI0_P, MDI1_N, MDI1_P, MDI2_N, MDI2_P, MDI3_N, MDI3_P, PHY0_N, PHY0_P, PHY1_N, PHY1_P, PHY2_N, PHY2_P, PHY3_N, PHY3_P, TD0_N, TD0_P, TD1_N, TD1_P, TD2_N, TD2_P, TD3_N, TD3_P

### Layout notes

- Each MDI pair: 100R differential impedance, length-matched within 0.5mm intra-pair, <= 2mm skew across the four pairs (rule) — _IEEE 802.3 Sec 40.7 + Pulse layout guide_
- CHASSIS_GND is an island bonded to signal GND only at a single star point near the carrier's power-entry connector (rule) — _EMC ground-loop avoidance + IEEE 802.3 Sec 14.7_
- Place magnetics within 30mm of the RJ45 connector and keep MDI traces straight from magnetics to jack (no vias) (rule) — _Pulse HX5008NL layout guide + minimise common-mode noise_
- Route the four Bob Smith 75R + 1nF/2kV networks together near the magnetics' line side; use the 2kV safety caps (NOT generic 1nF MLCCs) for IEC 60950 / IEEE 802.3 isolation compliance (rule) — _IEEE 802.3 Sec 40.7.1 + safety isolation_
- Keep PHY-side MDI traces (TD0..3 pairs) on a different copper layer or 3x spacing from the line-side MX traces to preserve the 1500 V_RMS hi-pot isolation through the magnetics (rule) — _HX5008NL DS Sheet 2 (1500 V_RMS minimum I/O isolation)_

## SW1 — DS-04P

**Block:** boot_switches  
**Datasheet:** [DS-04P](https://datasheet.lcsc.com/lcsc/Hanbo-Electronic-DS-04P_C18198092.pdf) (Boot-strap topology: pull-up + DIP-to-GND, DS-04P schematic p. 1 + Zynq-7000 TRM Sec 6.3.6 boot-mode strap usage)  
**Footprint:** Switch_SMD:DIP_Switch_x4  
**Supply rail:** +3V3  
**Min-circuit verified:** yes  

4-position SMD SPST DIP switch on 1.27 mm pitch (boot-mode straps)

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| SW1 | +3V3 | 10k_0402_1% | 1 | Zynq-7000 TRM Sec 6.3.6: strap pull-up (>=4.7k, <=20k) |
| SW2 | +3V3 | 10k_0402_1% | 1 | Zynq-7000 TRM Sec 6.3.6: strap pull-up |
| SW3 | +3V3 | 10k_0402_1% | 1 | Zynq-7000 TRM Sec 6.3.6: strap pull-up |
| SW4 | +3V3 | 10k_0402_1% | 1 | Zynq-7000 TRM Sec 6.3.6: strap pull-up |

### Pin overrides

| Pin | Net |
|---|---|
| SW1 | ZYNQ_BOOT_MODE_0 |
| SW2 | ZYNQ_BOOT_MODE_1 |
| SW3 | ZYNQ_BOOT_MODE_2 |
| SW4 | ZYNQ_BOOT_MODE_3 |

### No external required

_Pins explicitly left bare:_ GND

### Layout notes

- Place the 10k pull-ups within 10 mm of the DIP switch so the strap network is short and immune to coupling (rule) — _Zynq-7000 TRM Sec 6.3.6: strap timing margin at PS_POR_B release_
- Provide silkscreen labelling (1 / 2 / 3 / 4 and ON marking) so the boot mode is visible without instructions (rule) — _User-facing component requires legible orientation_
- Route strap traces to the SoM J1 mate via short, direct paths - do not loop or share vias with other PS signals (guideline)
- Boot straps are latched only at PS_POR_B release - the DIP switch is not hot-swappable. Document this in the user guide — _Zynq-7000 TRM Sec 6.3.6 timing_

## SW2 — TS-1002S-06026C

**Block:** boot_switches  
**Datasheet:** [TS-1002S-06026C](https://datasheet.lcsc.com/lcsc/XUNPU-TS-1002S-06026C_C455112.pdf) (Datasheet 'CIRCUIT DIAGRAM' + typical GPIO push-button topology, TS-1002S mechanical p. 1 + typical GPIO debounce topology)  
**Footprint:** Button_Switch_SMD:SW_SPST_Tactile_6x6mm  
**Supply rail:** +3V3  
**Min-circuit verified:** yes  

6x6 mm SMD momentary tactile switch (active-low GPIO input)

### External parts

| From pin | To net | Part token | Qty | Why |
|---|---|---|---|---|
| SW | +3V3 | 10k_0402_1% | 1 | GPIO pull-up: button shorts SW to GND when pressed |
| SW | GND | 100n_0402_X7R | 1 | Hardware debounce (RC ~ 1 ms with 10k pull-up) + ESD shunt at button face |

### Pin overrides

| Pin | Net |
|---|---|
| SW | ZYNQ_PS_SRST_N |

### No external required

_Pins explicitly left bare:_ GND

### Layout notes

- Place the 100 nF debounce cap within 5 mm of the switch so the RC network sees the bounce node directly (rule) — _Debounce cap must be local to be effective_
- Place the switch on the carrier edge or top side for user access; provide silkscreen labelling (e.g. 'PS_RST') (guideline)
- Route the GPIO trace from switch to host SoM as a short, low-impedance signal; avoid running it parallel to clocks (guideline) — _Tactile switches act as ESD entry points_
