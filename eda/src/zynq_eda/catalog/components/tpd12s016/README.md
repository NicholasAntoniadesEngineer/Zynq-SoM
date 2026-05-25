# TPD12S016PWR - HDMI companion (ESD + level shift + 5V switch)

Texas Instruments TPD12S016PWR (TSSOP-24, LCSC C201665) is the single-chip
HDMI port companion used on both HDMI lanes of the carrier. One die, two
refcircuits:

| Refcircuit                 | Role             | +5V handling                                 |
|----------------------------|------------------|-----------------------------------------------|
| `TPD12S016_TX_REFCIRCUIT`  | HDMI source (TX) | On-chip 55mA load switch sources +5V out      |
| `TPD12S016_RX_REFCIRCUIT`  | HDMI sink (RX)   | +5V sensed from upstream (back-drive protected)|

Datasheet (in this folder): TI SLLSE96F, Sep 2011 / Rev Oct 2015.

## Rails

| Rail        | Pin (PW)     | Direction | Notes                                                  |
|-------------|--------------|-----------|--------------------------------------------------------|
| `+3V3`      | VCCA (24)    | input     | Controller-side reference (1.1-3.6V range)             |
| `+5V` / src | VCC5V (11)   | input     | Load-switch input (TX) or sense-only input (RX)        |
| `5V_OUT`    | 5V_OUT (13)  | output    | Switched 55mA to HDMI connector +5V (TX role)          |
| `GND`       | 6, 14, 19    | -         | All three GND pins tied to the system ground plane     |

## Key external parts

Per DS Section 8 (Application) Figure 15 and Section 10 (Layout):

| From pin   | To net  | Part token         | Qty | Why                                              |
|------------|---------|--------------------|-----|--------------------------------------------------|
| VCCA       | GND     | `100n_0402_X7R`    | 1   | DS Fig 15: V_CCA bypass at pin 24                |
| VCC5V      | GND     | `100n_0402_X7R`    | 1   | DS Fig 15: V_CC5V bypass at pin 11               |
| CT_HPD     | +3V3    | `10k_0402_1%`      | 1   | DS Sec 8.2.1: CT_HPD = HIGH enables device       |

The TPD12S016 has integrated pull-ups on DDC SCL/SDA (1.75k to 5V_OUT
on the B-side, 10k to V_CCA on the A-side), CEC (26k to internal 3.3V
LDO) and HPD (11k pull-down on HPD_B), so NO external pull-ups are
needed on those lines (DS Section 7.3.9 and 7.3.15).

## Layout constraints

* Place the device within 10mm of the HDMI receptacle pin 1 - the ESD
  energy must dissipate at the protection pins, not travel further
  down unprotected PCB traces (DS Section 10.1).
* Route TMDS pairs as 100 ohm differential, length-matched within
  0.5mm intra-pair and <= 2mm inter-pair skew (HDMI 1.4 Sec 4.2.3).
* No vias between connector and the TPD12S016 protection pins; no
  90-degree turns on TMDS traces (DS Section 10.1).
* Place decoupling caps within 5mm of V_CCA (pin 24) and V_CC5V (pin
  11). Tie all three GND pins via a generous via field to a continuous
  ground plane.

## Carrier usage

* `blocks/hdmi_tx.py` instantiates `TPD12S016PWR_TX` between the
  Zynq HDMI source and the HDMI Type-A connector. The on-chip 5V
  load switch sources VBUS to the connector's pin 18 (gated by the
  CT_HPD pull-up).
* `blocks/hdmi_rx.py` instantiates `TPD12S016PWR_RX` between the
  HDMI Type-A connector and the Zynq HDMI sink. The +5V coming IN
  from the upstream source on connector pin 18 lands on V_CC5V via
  the (open) 5V_OUT pin; TPD12S016 back-drive protection (DS Sec
  7.3.8) prevents reverse current into our +5V rail.
