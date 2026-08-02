from __future__ import annotations

from schgen.core.basis import SOURCE_CLASSES, Registry

_CLASSES = SOURCE_CLASSES
_UNITS = ("ohm", "F", "H", "Hz")

_BASIS = Registry(units=_UNITS)
REGISTRY = _BASIS.entries
_register = _BASIS.register


CAMERA_LANE_TERM = _register(
    "CAMERA_LANE_TERM", "100R", "ohm",
    "Xilinx XAPP894 '7-series + external passives' D-PHY topology: an HR bank "
    "cannot switch DIFF_TERM, so each CSI-2 pair carries a fixed external 100 "
    "ohm differential termination at the receiver end of the trace.",
    "datasheet")

CAMERA_I2C_PULL = _register(
    "CAMERA_I2C_PULL", "4k7", "ohm",
    "MIPI CCI / I2C Rp on the gated +VDD_CAM rail. NXP UM10204 eq 2 gives "
    "Rp(max) = tr / (0.8473 * Cb); at Fast-mode 400 kHz (tr 300 ns) 4k7 holds "
    "for Cb <= 75 pF, which the short FFC control pair meets. House value "
    "shared with the lcd touch bus; the bus is dead without it (open drain).",
    "policy")

CAMERA_RAIL_BYPASS = _register(
    "CAMERA_RAIL_BYPASS", "100n", "F",
    "HF bypass at the FFC power pin (J1.15) on the gated camera rail.",
    "policy")

CAMERA_RAIL_BULK = _register(
    "CAMERA_RAIL_BULK", "10u", "F",
    "Local bulk at the FFC for the RPi V2/IMX219 ~250 mA module budget; the "
    "peer FFC subsystems (lcd, microsd) carry the same 10u at the connector.",
    "policy")

ETHERNET_BOB_SMITH_R = _register(
    "ETHERNET_BOB_SMITH_R", "75R", "ohm",
    "IEEE 802.3 section 40.7.1 Bob-Smith HF termination: each MEDIA centre tap "
    "sees 75 ohm (half the 150 ohm common-mode impedance of a UTP pair) into "
    "the shared trunk. LCSC C4275.",
    "datasheet")

ETHERNET_BOB_SMITH_C = _register(
    "ETHERNET_BOB_SMITH_C", "1n", "F",
    "Bob-Smith trunk cap and the single BS_COMMON -> CHASSIS_GND isolation "
    "element. GENUINE 1 nF / 2 kV X7R (IEC 60950/62368 hi-pot), 1206 body for "
    "the 2 kV rating; LCSC C9196 (FH 1206B102K202NT), JLC Basic.",
    "datasheet")

HDMI_RX_HPD_ASSERT = _register(
    "HDMI_RX_HPD_ASSERT", "1k", "ohm",
    "HDMI 1.4 section 4.2.6 passive hot-plug assert: the cable's own +5V "
    "(pin 18) is returned to HPD (pin 19) through 1 kohm, so a plugged source "
    "sees HPD high and reads EDID with the consuming board unpowered.",
    "datasheet")

HDMI_RX_CEC_PULL = _register(
    "HDMI_RX_CEC_PULL", "27k", "ohm",
    "HDMI 1.4 CEC Supplement 1: the CEC line carries a 27 kohm pull-up to the "
    "device's 3.3 V supply. Here the gated module rail +VDD_LOGIC.",
    "datasheet")

HDMI_RX_DET_TOP = _register(
    "HDMI_RX_DET_TOP", "10k", "ohm",
    "Cable-5V presence divider, top leg. With the 15k bottom leg the worst-case "
    "cable rail 5.25 V presents 5.25*15/25 = 3.15 V at HDMI_5V_DET — inside "
    "LVCMOS33 abs-max, so the detect line is safe on a 3.3 V bank.",
    "datasheet")

HDMI_RX_DET_BOTTOM = _register(
    "HDMI_RX_DET_BOTTOM", "15k", "ohm",
    "Cable-5V presence divider, bottom leg; the 10k/15k ratio sets the 3.15 V "
    "worst-case output (see HDMI_RX_DET_TOP).",
    "datasheet")

HDMI_RX_EDID_BYPASS = _register(
    "HDMI_RX_EDID_BYPASS", "100n", "F",
    "M24C02 EDID EEPROM VCC bypass on the cable-5V quasi-rail.",
    "policy")

HDMI_TX_RAIL_BYPASS = _register(
    "HDMI_TX_RAIL_BYPASS", "100n", "F",
    "TI TPD12S016 SLLSE96F Figure 15: 100 nF on V_CCA (pin 24) and on V_CC5V "
    "(pin 11).",
    "datasheet")

HDMI_TX_RAIL_BULK = _register(
    "HDMI_TX_RAIL_BULK", "10u", "F",
    "Module bulk on the +VDD_IO controller rail; the peer connector subsystems "
    "(camera, microsd) carry the same 10u per module rail.",
    "policy")

HDMI_TX_CABLE_BYPASS = _register(
    "HDMI_TX_CABLE_BYPASS", "100n", "F",
    "HDMI 1.4 section 4.2.7: HF decoupling on the source's switched +5V at the "
    "receptacle (pin 18).",
    "datasheet")

HDMI_TX_CABLE_BULK = _register(
    "HDMI_TX_CABLE_BULK", "1u", "F",
    "HDMI 1.4 section 4.2.7 bulk companion to the 100 nF at the receptacle "
    "+5V pin.",
    "datasheet")

HDMI_TX_STRAP_PULL = _register(
    "HDMI_TX_STRAP_PULL", "10k", "ohm",
    "TI TPD12S016 SLLSE96F Figure 15 / section 8.2.1 'HDMI source using one "
    "GPIO': LS_OE (pin 5) and CT_HPD (pin 12) strapped HIGH through 10 kohm to "
    "V_CCA so the level shifters and the 55 mA +5V switch are always on.",
    "datasheet")

LCD_ISET_SENSE = _register(
    "LCD_ISET_SENSE", "1.5R", "ohm",
    "Silergy SY7201 WLED-boost current set: I_LED = V_FB / R_ISET with "
    "V_FB = 0.2 V, so 0.2/1.5 = 133 mA into the LED string.",
    "datasheet")

LCD_BOOST_INDUCTOR = _register(
    "LCD_BOOST_INDUCTOR", "10uH", "H",
    "SY7201 application inductor (SWPA4030S100MT, 10 uH).",
    "datasheet")

LCD_BOOST_CIN = _register(
    "LCD_BOOST_CIN", "10u", "F",
    "SY7201 boost input bulk per the application circuit (10u + 1u at IN).",
    "datasheet")

LCD_BOOST_HF = _register(
    "LCD_BOOST_HF", "1u", "F",
    "SY7201 dedicated HF ceramic at the IN pin; the application circuit "
    "specifies 10u + 1u and only the 10u was fitted (audit 2026-06-20).",
    "datasheet")

LCD_BOOST_COUT = _register(
    "LCD_BOOST_COUT", "2.2u", "F",
    "SY7201 boost output cap on LCD_VLED_P, 50 V X7R (LCSC C125847). The node "
    "resolves to the 30 V open-LED OVP clamp; continuous string voltage is "
    "~9.6 V, so the 50 V part carries the rare fault transient with the 2x "
    "MLCC derate applied to the continuous bias (LCD-1).",
    "datasheet")

LCD_PANEL_BYPASS = _register(
    "LCD_PANEL_BYPASS", "100n", "F",
    "Panel VDD HF bypass at the FFC on the gated +VDD_LCD rail "
    "(lcd_backlight.md 3.1: '10uF + 100n').",
    "datasheet")

LCD_PANEL_BULK = _register(
    "LCD_PANEL_BULK", "10u", "F",
    "Panel VDD bulk (lcd_backlight.md 3.1: '10uF + 100n'); only the 100n was "
    "present, the peers camera/microsd carry 10u.",
    "datasheet")

LCD_TOUCH_PULL = _register(
    "LCD_TOUCH_PULL", "4k7", "ohm",
    "Capacitive-touch I2C Rp to the gated +VDD_LCD. NXP UM10204 eq 2 gives "
    "Rp(max) = tr / (0.8473 * Cb); at Fast-mode 400 kHz (tr 300 ns) 4k7 holds "
    "for Cb <= 75 pF. Open-drain bus: without these the bus is dead.",
    "policy")

LCD_RESET_PULLDOWN = _register(
    "LCD_RESET_PULLDOWN", "100k", "ohm",
    "Touch-controller reset held asserted until the host releases it — a "
    "driven reset, not an RC reset, so no cap-to-GND by design.",
    "policy")

LCD_DISP_PULLUP = _register(
    "LCD_DISP_PULLUP", "10k", "ohm",
    "Panel display-enable defaults ON whenever the gated rail is up.",
    "policy")

LCD_PCLK_DAMPING = _register(
    "LCD_PCLK_DAMPING", "22R", "ohm",
    "Source-series damping on the ~33 MHz pixel clock, the highest-edge-rate "
    "line on the FFC; the resistor sits at the host/source end so the series "
    "sum approaches the ~50 ohm trace impedance.",
    "policy")

LCD_BLPWM_PULLDOWN = _register(
    "LCD_BLPWM_PULLDOWN", "100k", "ohm",
    "SY7201 EN/PWM held low so the backlight boost is OFF until the host "
    "drives it high.",
    "policy")

MICROSD_CARD_PULL = _register(
    "MICROSD_CARD_PULL", "100k", "ohm",
    "TI SCEA054A: the TXS02612 B0 one-shot outputs already hold an internal "
    "pull-up (4 kohm high / 40 kohm low, fig.1). An external pull parallels "
    "the internal 40 kohm while driving low — Table 1 measures VOL 29 mV (no "
    "pull) -> 169 mV (~10k) -> 38 mV (100k), guidance '>50 kohm beneficial'. "
    "100k keeps an SD-spec anti-float pull inside that band. LCSC C25803.",
    "datasheet")

MICROSD_DETECT_PULL = _register(
    "MICROSD_DETECT_PULL", "10k", "ohm",
    "Card-detect pull-up. NOT on a TXS02612 output, so the SCEA054A >50 kohm "
    "rule does not apply and the plain 10k anti-float value stands.",
    "policy")

MICROSD_HOST_BYPASS = _register(
    "MICROSD_HOST_BYPASS", "100n", "F",
    "TXS02612 VCCA (host-side) local bypass.",
    "policy")

MICROSD_CARD_BYPASS = _register(
    "MICROSD_CARD_BYPASS", "100n", "F",
    "Card-rail HF bypass (VCCB0/VCCB1 + slot VDD).",
    "policy")

MICROSD_CARD_BULK = _register(
    "MICROSD_CARD_BULK", "22u", "F",
    "Card-rail bulk sized for SD write bursts: the SD physical spec allows "
    "~200 mA on the card supply, and the budgeted draw is 250 mA.",
    "datasheet")

MICROSD_ESD_BYPASS = _register(
    "MICROSD_ESD_BYPASS", "100n", "F",
    "TI SLLS546: the TPD6E001 VCC sets the clamp reference; a floating VCC "
    "gives the worst-case clamp, so VCC is biased to the card rail and "
    "bypassed locally (SD-1).",
    "datasheet")

PD_INPUT_INLET_BYPASS = _register(
    "PD_INPUT_INLET_BYPASS", "100n", "F",
    "TPS26631 datasheet-minimum input capacitance at the raw receptacle VBUS, "
    "alongside the SMBJ22A TVS.",
    "datasheet")

PD_INPUT_OVP_TOP = _register(
    "PD_INPUT_OVP_TOP", "100k", "ohm",
    "TPS26631 OVP divider, top leg from +VBUS_CONN. With the 5.49k bottom leg "
    "the OVP trip is 23.06 V typ — above the 21 V worst-case 20 V PD contract "
    "and below the downstream 24 V-class limits (PD-1 widened the window).",
    "datasheet")

PD_INPUT_OVP_BOTTOM = _register(
    "PD_INPUT_OVP_BOTTOM", "5.49k", "ohm",
    "TPS26631 OVP divider, bottom leg; the 100k/5.49k ratio sets the 23.06 V "
    "typ trip (PD-1). LCSC C188263.",
    "datasheet")

PD_INPUT_ILIM_SET = _register(
    "PD_INPUT_ILIM_SET", "5.1k", "ohm",
    "TPS26631 current limit: I_OL = 18 / R_ILIM(kohm) = 18/5.1 = 3.5 A, above "
    "the 3 A PD contract with margin.",
    "datasheet")

PD_INPUT_DVDT_CAP = _register(
    "PD_INPUT_DVDT_CAP", "47n", "F",
    "TPS26631 dVdT soft-start cap; 47 nF sets a 1.02 V/ms output slew, so the "
    "downstream bulk charges without tripping the current limit.",
    "datasheet")

PD_INPUT_FAULT_PULL = _register(
    "PD_INPUT_FAULT_PULL", "100k", "ohm",
    "Open-drain FLT# pull-up to the always-on +VDD_LOGIC (never the 20 V inlet "
    "VBUS — an expander IO abs-max is far below the PD contract).",
    "policy")

PD_INPUT_FUSED_BULK = _register(
    "PD_INPUT_FUSED_BULK", "10u", "F",
    "The dVdT-charged board bulk behind the eFuse; 1210 50 V X7R (LCSC "
    "C596319) for the 21 V worst-case rail.",
    "datasheet")

PMOD_SERIES_DAMPING = _register(
    "PMOD_SERIES_DAMPING", "200R", "ohm",
    "Digilent Pmod specification: each host IO carries a 200 ohm series "
    "protection resistor between the host signal and the socket pin. LCSC "
    "C8218.",
    "datasheet")

PMOD_RAIL_BYPASS = _register(
    "PMOD_RAIL_BYPASS", "100n", "F",
    "Per-port HF bypass at the Pmod VCC pins (positions 6/12).",
    "policy")

PMOD_RAIL_BULK = _register(
    "PMOD_RAIL_BULK", "10u", "F",
    "Per-port bulk for the Digilent ~100 mA per-module budget.",
    "policy")

PMOD_EXP_ILIM_SET = _register(
    "PMOD_EXP_ILIM_SET", "13k", "ohm",
    "Silergy SY6280 current limit: I_LIM = 6800 / R_ISET(kohm) = 6800/13 = "
    "523 mA, above the Digilent ~100 mA per-module budget with margin. LCSC "
    "C22797.",
    "datasheet")

PMOD_EXP_INPUT_BYPASS = _register(
    "PMOD_EXP_INPUT_BYPASS", "100n", "F",
    "HF bypass at the SY6280 IN pin, ahead of the 10u input bulk.",
    "policy")

PMOD_EXP_INPUT_BULK = _register(
    "PMOD_EXP_INPUT_BULK", "10u", "F",
    "SY6280 datasheet Pin Description ('IN ... decoupled with a 10uF capacitor "
    "to GND') and Application Information ('a 10uF ceramic capacitor from VIN "
    "to GND is strongly recommended'): without it an output short rings the "
    "input, and the rail bulk sits upstream of the inlet shunt.",
    "datasheet")

PMOD_EXP_OUTPUT_BYPASS = _register(
    "PMOD_EXP_OUTPUT_BYPASS", "100n", "F",
    "SY6280 OUT-pin HF bypass; the datasheet 10u OUT bulk is met by the socket "
    "bulk on the same +VSW_PMOD net.",
    "datasheet")

PMOD_EXP_ENABLE_PULLDOWN = _register(
    "PMOD_EXP_ENABLE_PULLDOWN", "100k", "ohm",
    "Holds SY6280 EN low so the port is dark at power-up until the DSHP04 "
    "switch is closed by hand — a peripheral cannot be back-fed.",
    "policy")

PMOD_EXP_LED_SERIES = _register(
    "PMOD_EXP_LED_SERIES", "330R", "ohm",
    "Status LED on the gated 3.3 V output: (3.3 - 2.0)/330 = 3.9 mA through "
    "the KT-0603R red LED.",
    "policy")

PMOD_EXP_SOCKET_BYPASS = _register(
    "PMOD_EXP_SOCKET_BYPASS", "100n", "F",
    "HF bypass at the Pmod VCC pins (positions 6/12).",
    "policy")

PMOD_EXP_SOCKET_BULK = _register(
    "PMOD_EXP_SOCKET_BULK", "10u", "F",
    "Socket bulk for the Digilent ~100 mA module budget; also serves as the "
    "SY6280 OUT bulk (same net).",
    "datasheet")

POWER_VIN_HF = _register(
    "POWER_VIN_HF", "100n", "F",
    "TI SNVSBD5D 9.2.2.5 requires a 100 nF at EACH VIN/PGND pin pair "
    "immediately adjacent to the LM61460, rated 50 V with X7R or better. LCSC "
    "C14663 (CC0603KRX7R9BB104, 100 nF 50 V X7R) meets the rule; the VQFN-HR "
    "splits VIN/PGND across opposite package sides so one goes at each.",
    "datasheet")

POWER_VIN_BULK = _register(
    "POWER_VIN_BULK", "10u", "F",
    "SNVSBD5D 9.2.2.5 '>=10 uF ceramic at the input'; 2x 1206 50 V-class for "
    "the 21 V +VIN rail.",
    "datasheet")

POWER_5V_BULK = _register(
    "POWER_5V_BULK", "22u", "F",
    "Input bulk for the +3V3 buck off the board +5V rail (SNVSBD5D 9.2.2.5); "
    "0805 25 V-class, 2 pieces.",
    "datasheet")

POWER_VCC_BYPASS = _register(
    "POWER_VCC_BYPASS", "1u", "F",
    "SNVSBD5D 9.2.2.8: 1 uF from VCC (pin 2) to AGND, the internal-LDO bypass, "
    "16 V ceramic.",
    "datasheet")

POWER_BIAS_SERIES = _register(
    "POWER_BIAS_SERIES", "10R", "ohm",
    "SNVSBD5D 9.2.2.9: 'a series resistor, 1 ohm to 10 ohm, can be added "
    "between VOUT and BIAS'. Top of the band for maximum noise filtering; the "
    "BIAS LDO sink current is small so the IR drop is negligible. LCSC C22859.",
    "datasheet")

POWER_BIAS_BYPASS = _register(
    "POWER_BIAS_BYPASS", "1u", "F",
    "SNVSBD5D 9.2.2.9: 'a bypass capacitor of 1 uF or higher can be added "
    "close to the BIAS pin'.",
    "datasheet")

POWER_RT_FREQ = _register(
    "POWER_RT_FREQ", "22k", "ohm",
    "SNVSBD5D Eq 2: R_RT(kohm) = (1/fSW(kHz) - 3.3e-5) * 1.346e4, so 600 kHz "
    "gives 21.99k ~= 22.0k. 600 kHz keeps the existing 10 uH SWPA8040S within "
    "its 4 A Isat on both stages. LCSC C31850.",
    "datasheet")

POWER_BOOT_CAP = _register(
    "POWER_BOOT_CAP", "100n", "F",
    "SNVSBD5D 9.2.2.6: 100 nF SW->CBOOT, X7R >=10 V. 9.2.2.7 allows RBOOT "
    "shorted to CBOOT, so pins 13/14 are one node and no boot resistor exists.",
    "datasheet")

POWER_SW_INDUCTOR = _register(
    "POWER_SW_INDUCTOR", "10uH", "H",
    "SNVSBD5D 9.2.2.3 Eq 11 minimum at D<50% is L >= 0.2*Vout/fSW = "
    "0.2*5/600k = 1.67 uH; 10 uH is well above it so the loop is stable with "
    "no subharmonic oscillation. Ripple dIL = 0.63 A p-p at 5 V (Ipk 3.27 A) "
    "and 0.187 A p-p at 3.3 V (Ipk 2.84 A), both under the 4 A Isat of the "
    "SWPA8040S (LCSC C37429).",
    "datasheet")

POWER_COUT_BULK = _register(
    "POWER_COUT_BULK", "22u", "F",
    "SNVSBD5D Table 9-5 (5 V application BOM) and Table 9-3 both list 3x 22 uF "
    "COUT at 5 V; 9.2.2.3 notes a larger-than-minimum inductor needs MORE "
    "output capacitance for transients, which the 10 uH choice makes the "
    "dominant term. 25 V Basic 0805, LCSC C45783.",
    "datasheet")

POWER_FB5V_TOP = _register(
    "POWER_FB5V_TOP", "40.2k", "ohm",
    "SNVSBD5D 8.3.11 Vref = 1.0 V, Vout = 1.0*(1 + Rtop/Rbot): 40.2k/10k -> "
    "5.02 V. LCSC C12447 (UNI-ROYAL 0603WAF4022T5E, 40.2k 0603 1%). "
    "BOM-CRITICAL: the prior C25750 was a mis-key resolving to a 120k 0402, "
    "which would set ~13.1 V on the +5V rail.",
    "datasheet")

POWER_FB3V3_TOP = _register(
    "POWER_FB3V3_TOP", "23.2k", "ohm",
    "SNVSBD5D 8.3.11 Vref = 1.0 V: 23.2k/10k -> 3.32 V, worst case ~[3.24, "
    "3.40], centred in the +-3% window [3.201, 3.399]. Replaced 22.1k, whose "
    "3.21 V nominal left only ~3.13 V against the 3.135 V floor. LCSC C23346.",
    "datasheet")

POWER_FB_BOTTOM = _register(
    "POWER_FB_BOTTOM", "10k", "ohm",
    "Common FB-divider bottom leg for both LM61460 stages; the ratio against "
    "the per-stage top leg sets Vout (SNVSBD5D 8.3.11). LCSC C25804.",
    "datasheet")

POWER_CFF_CAP = _register(
    "POWER_CFF_CAP", "22p", "F",
    "SNVSBD5D 9.2.2.10 feedforward across the FB-top resistor for phase margin "
    "with low-ESR ceramic COUT. Tables 9-2 and 9-5 both list CFF = 22 pF at "
    "5 V. The ESR zero of a ceramic COUT is well above the 200 kHz no-CFF "
    "threshold, and both Vout are below the 14 V no-CFF ceiling.",
    "datasheet")

POWER_RFF_SERIES = _register(
    "POWER_RFF_SERIES", "1k", "ohm",
    "SNVSBD5D 9.2.2.10: 'a 1-kohm resistor, RFF, can be placed in series with "
    "CFF' because CFF conducts output noise straight to FB. Table 9-2 5 V row "
    "lists RFF = 1 kohm.",
    "datasheet")

POWER_LED5V_SERIES = _register(
    "POWER_LED5V_SERIES", "1k", "ohm",
    "Rail-up indicator on the 5 V regulator-side node: (5.0 - 2.0)/1000 = "
    "3.0 mA through the red LED.",
    "policy")

POWER_LED_SERIES = _register(
    "POWER_LED_SERIES", "330R", "ohm",
    "Rail-up indicator on the 3.3 V-class nodes: (3.3 - 2.0)/330 = 3.9 mA "
    "through the red LED.",
    "policy")

POWER_LDO_CAP = _register(
    "POWER_LDO_CAP", "1u", "F",
    "AP2112K input and output capacitance: the datasheet requires >=1 uF on "
    "both, and the LDO is stable with a 1 uF ceramic output cap.",
    "datasheet")

POWER_GATE_STOP = _register(
    "POWER_GATE_STOP", "1k", "ohm",
    "AO3400A gate-stop for the +1V8 PG sense cell. PWR-6: with the 100k "
    "pulldown a 10k series made Vgs = 1.8*100/110 = 1.64 V, barely over the "
    "1.45 V max Vgs(th); 1k gives 1.8*100/101 = 1.78 V and is a pure RC "
    "gate-stop rather than a divider.",
    "measured")

POWER_GATE_PULLDOWN = _register(
    "POWER_GATE_PULLDOWN", "100k", "ohm",
    "AO3400A gate pulldown holding the +1V8 sense FET off until the rail is "
    "up; sets the divider ratio in PWR-6 above.",
    "policy")

RJ45_LED_SERIES = _register(
    "RJ45_LED_SERIES", "330R", "ohm",
    "The two LEDs integrated in the KH-5224 housing driven as a steady "
    "port-present indicator off the always-on +VLED: (3.3 - 2.0)/330 = 4 mA "
    "each. LCSC C23138.",
    "policy")

UART_BRIDGE_SUPPLY_BYPASS = _register(
    "UART_BRIDGE_SUPPLY_BYPASS", "100n", "F",
    "SiLabs CP2102N self-powered reference: 100 nF on each of VREGIN (pin 7), "
    "VDD (pin 6) and VIO (pin 5).",
    "datasheet")

UART_BRIDGE_VREGIN_BULK = _register(
    "UART_BRIDGE_VREGIN_BULK", "10u", "F",
    "CP2102N self-powered reference bulk on VREGIN alongside the 100 nF.",
    "datasheet")

UART_BRIDGE_RESET_PULL = _register(
    "UART_BRIDGE_RESET_PULL", "1k", "ohm",
    "CP2102N ~RST is open-drain and needs an external pull to VDD33; the part "
    "carries its own internal POR so no RC cap is fitted.",
    "datasheet")

UART_BRIDGE_SENSE_TOP = _register(
    "UART_BRIDGE_SENSE_TOP", "22k1", "ohm",
    "CP2102N self-powered VBUS-sense divider, top leg from the UART "
    "receptacle's own 5 V VBUS. With the 47k5 bottom leg the pin sees "
    "5*47.5/69.6 = 3.41 V, inside the 5.8 V abs-max. LCSC C25961.",
    "datasheet")

UART_BRIDGE_SENSE_BOTTOM = _register(
    "UART_BRIDGE_SENSE_BOTTOM", "47k5", "ohm",
    "CP2102N VBUS-sense divider, bottom leg (see UART_BRIDGE_SENSE_TOP). LCSC "
    "C23061.",
    "datasheet")

JTAG_LDO_CIN = _register(
    "JTAG_LDO_CIN", "1u", "F",
    "AP2112K input capacitance for the self-powered island LDO (datasheet "
    "minimum 1 uF).",
    "datasheet")

JTAG_LDO_COUT = _register(
    "JTAG_LDO_COUT", "10u", "F",
    "AP2112K output bulk; the datasheet minimum is 1 uF and 10 uF carries the "
    "CH347 + buffer + pull network on the island rail.",
    "datasheet")

JTAG_SUPPLY_BYPASS = _register(
    "JTAG_SUPPLY_BYPASS", "100n", "F",
    "CH347 datasheet section 5.1 (~0.1 uF on VCC), plus the same HF bypass on "
    "the SN74LVC125 VCC and the island LDO output.",
    "datasheet")

JTAG_CRYSTAL_FREQ = _register(
    "JTAG_CRYSTAL_FREQ", "8MHz", "Hz",
    "CH347 datasheet section 5.1 clock: 8 MHz crystal on XI/XO (KDS "
    "1C208000BC0R, LCSC C57131).",
    "datasheet")

JTAG_CRYSTAL_LOAD = _register(
    "JTAG_CRYSTAL_LOAD", "16p", "F",
    "The CH347 datasheet 5.1 '~22 pF' is boilerplate for a CL=20 pF crystal. "
    "The fitted 1C208000BC0R is cut for CL=12 pF, so Cext = 2*(CL - Cstray) = "
    "2*(12 - ~4) = 16 pF C0G per leg; 22 pF would over-load it and pull 8 MHz "
    "slow. LCSC C162205.",
    "datasheet")

JTAG_RESET_PULL = _register(
    "JTAG_RESET_PULL", "10k", "ohm",
    "CH347 RST# (pin 1) already carries an internal pull-up and a built-in "
    "power-on reset (DS 5.1); the external 10k is noise-immunity insurance and "
    "no RC cap is fitted.",
    "datasheet")

JTAG_MODE_PULLDOWN = _register(
    "JTAG_MODE_PULLDOWN", "10k", "ohm",
    "CH347 DS section 5.2 mode table: MODE 3 (JTAG + UART) needs DTR1 (pin 10) "
    "and RTS1 (pin 13) both pulled LOW at power-on reset. Both pins carry "
    "built-in pull-ups of ~40 kohm, so a 10k external pulldown dominates.",
    "datasheet")

JTAG_OE_PULLUP = _register(
    "JTAG_OE_PULLUP", "100k", "ohm",
    "Default-OFF isolation: all four SN74LVC125 OE# pins are held HIGH (outputs "
    "Hi-Z) through 100k to the island rail until SW1 pulls them to GND, so a "
    "pod on the target JTAG header never contends with the bridge.",
    "policy")

JTAG_CONN_VBUS_BULK = _register(
    "JTAG_CONN_VBUS_BULK", "10u", "F",
    "USB-C UFP VBUS bulk/bypass at the receptacle; the board-standard 0805 "
    "25 V part (LCSC C15850).",
    "policy")

JTAG_CONN_CC_RD = _register(
    "JTAG_CONN_CC_RD", "5.1k", "ohm",
    "USB Type-C specification device/UFP role: one Rd = 5.1 kohm +-20% per CC "
    "pin to GND, which tells a source to apply VBUS. LCSC C23186 is a 5% "
    "Basic part, inside the +-20% spec.",
    "datasheet")

USB_PD_VDD_BYPASS = _register(
    "USB_PD_VDD_BYPASS", "100n", "F",
    "onsemi FUSB302B reference circuit: 100 nF HF on VDD.",
    "datasheet")

USB_PD_VDD_BULK = _register(
    "USB_PD_VDD_BULK", "10u", "F",
    "FUSB302B reference circuit: 10 uF bulk companion on VDD.",
    "datasheet")

USB_PD_VBUS_BYPASS = _register(
    "USB_PD_VBUS_BYPASS", "100n", "F",
    "FUSB302B reference circuit: 100 nF on the VBUS-sense pin (U1.2), whose "
    "abs-max is 28 V.",
    "datasheet")

USB_PD_CC_FILTER = _register(
    "USB_PD_CC_FILTER", "200p", "F",
    "FUSB302B reference circuit: 200 pF analog filter from each CC line to "
    "GND. NP0 0603 (LCSC C113796) so the BMC edge is not distorted by "
    "dielectric loss.",
    "datasheet")

UART_CONN_VBUS_BULK = _register(
    "UART_CONN_VBUS_BULK", "10u", "F",
    "USB-C UFP VBUS decoupling (Cbus) at the receptacle; the board-standard "
    "0805 25 V part (LCSC C15850) against the 5.25 V worst-case rail.",
    "datasheet")

UART_CONN_CC_RD = _register(
    "UART_CONN_CC_RD", "5.1k", "ohm",
    "USB Type-C specification device/UFP role: one Rd = 5.1 kohm +-20% per CC "
    "pin; a source's Rp plus this Rd forms the attach divider. LCSC C23186 "
    "(0603WAF5101T5E, 5% Basic) is inside the spec tolerance.",
    "datasheet")

OTG_INPUT_BYPASS = _register(
    "OTG_INPUT_BYPASS", "100n", "F",
    "TI TPS2051C input bypass at the switch IN pin.",
    "datasheet")

OTG_VBUS_MLCC = _register(
    "OTG_VBUS_MLCC", "22u", "F",
    "HF companion on the sourced VBUS. MLCC alone is not enough: at 5 V bias "
    "it derates to ~15-20 uF, below the USB 2.0 host-port 120 uF minimum and "
    "the TPS2051C datasheet 150 uF reference, so the bulk is carried by the "
    "electrolytic instead (more MLCC would only re-derate).",
    "datasheet")

OTG_VBUS_BULK = _register(
    "OTG_VBUS_BULK", "100u", "F",
    "DMBJ RVT1C101M0605 100 uF 16 V aluminium electrolytic (LCSC C970684): "
    "its capacitance does NOT bias-derate, so it holds VBUS above 4.4 V "
    "through a device hot-plug. Pad 1 = +, pad 2 = -.",
    "datasheet")

OTG_ENABLE_PULLDOWN = _register(
    "OTG_ENABLE_PULLDOWN", "100k", "ohm",
    "TPS2051C EN is active-high; the pulldown holds the host VBUS switch OFF "
    "until the host drives VBUS_EN, so the port cannot source 5 V at power-on "
    "before the OTG role is decided.",
    "policy")

OTG_FAULT_PULLUP = _register(
    "OTG_FAULT_PULLUP", "100k", "ohm",
    "TPS2051C FLT# is open-drain; the pull-up rails to +VDD_LOGIC so the flag "
    "stays inside the reader's IO abs-max and remains readable when the "
    "+VBUS_SUPPLY module rail is gated off.",
    "policy")

OTG_CC_RP = _register(
    "OTG_CC_RP", "56k", "ohm",
    "USB Type-C specification host/DFP role: Rp = 56 kohm +-20% per CC pin to "
    "VBUS advertises Default USB power. LCSC C23206 (0603WAF5602T5E, 1%).",
    "datasheet")

OTG_ID_STRAP = _register(
    "OTG_ID_STRAP", "1k", "ohm",
    "OTG ID strapped to GND through 1 kohm = HOST role for this port; the "
    "series resistance limits current if a host drives the ID line.",
    "policy")
