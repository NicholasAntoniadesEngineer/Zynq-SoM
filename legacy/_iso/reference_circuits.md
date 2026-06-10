# Carrier Reference Circuits

Auto-generated design-intent record. For every IC on the carrier, this document shows the manufacturer reference circuit applied: every external part required by the datasheet, pin overrides, and layout notes. The EE reviews this document before PCB tape-out to confirm the carrier design follows each IC's reference design.

## Contents

- [U1 — TLV75733PDBVR](#u1-tlv75733pdbvr)
- [U2 — TLV75725PDBVR](#u2-tlv75725pdbvr)
- [U3 — TLV75718PDBVR](#u3-tlv75718pdbvr)
- [U1 — FUSB302BMPX](#u1-fusb302bmpx)
- [U2 — USBLC6-4SC6](#u2-usblc6-4sc6)
- [T1 — HX5008NLT](#t1-hx5008nlt)

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

| Pin | Net |
|---|---|
| PHY0_P | ZYNQ_ETH_MDI_0_P |
| PHY0_N | ZYNQ_ETH_MDI_0_N |
| PHY1_P | ZYNQ_ETH_MDI_1_P |
| PHY1_N | ZYNQ_ETH_MDI_1_N |
| PHY2_P | ZYNQ_ETH_MDI_2_P |
| PHY2_N | ZYNQ_ETH_MDI_2_N |
| PHY3_P | ZYNQ_ETH_MDI_3_P |
| PHY3_N | ZYNQ_ETH_MDI_3_N |
| TD0_P | ETH_LINE_MDI_0_P |
| TD0_N | ETH_LINE_MDI_0_N |
| TD1_P | ETH_LINE_MDI_1_P |
| TD1_N | ETH_LINE_MDI_1_N |
| TD2_P | ETH_LINE_MDI_2_P |
| TD2_N | ETH_LINE_MDI_2_N |
| TD3_P | ETH_LINE_MDI_3_P |
| TD3_N | ETH_LINE_MDI_3_N |

### No external required

_Pins explicitly left bare:_ MDI0_N, MDI0_P, MDI1_N, MDI1_P, MDI2_N, MDI2_P, MDI3_N, MDI3_P, PHY0_N, PHY0_P, PHY1_N, PHY1_P, PHY2_N, PHY2_P, PHY3_N, PHY3_P, TD0_N, TD0_P, TD1_N, TD1_P, TD2_N, TD2_P, TD3_N, TD3_P

### Layout notes

- Each MDI pair: 100R differential impedance, length-matched within 0.5mm intra-pair, <= 2mm skew across the four pairs (rule) — _IEEE 802.3 Sec 40.7 + Pulse layout guide_
- CHASSIS_GND is an island bonded to signal GND only at a single star point near the carrier's power-entry connector (rule) — _EMC ground-loop avoidance + IEEE 802.3 Sec 14.7_
- Place magnetics within 30mm of the RJ45 connector and keep MDI traces straight from magnetics to jack (no vias) (rule) — _Pulse HX5008NL layout guide + minimise common-mode noise_
- Route the four Bob Smith 75R + 1nF/2kV networks together near the magnetics' line side; use the 2kV safety caps (NOT generic 1nF MLCCs) for IEC 60950 / IEEE 802.3 isolation compliance (rule) — _IEEE 802.3 Sec 40.7.1 + safety isolation_
- Keep PHY-side MDI traces (TD0..3 pairs) on a different copper layer or 3x spacing from the line-side MX traces to preserve the 1500 V_RMS hi-pot isolation through the magnetics (rule) — _HX5008NL DS Sheet 2 (1500 V_RMS minimum I/O isolation)_
