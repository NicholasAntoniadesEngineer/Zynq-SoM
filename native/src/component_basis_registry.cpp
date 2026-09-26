#include "schgen/component_basis.hpp"

namespace schgen {
const ComponentBasisPolicy& default_component_basis_policy() {
    static const ComponentBasisPolicy policy = [] {
        ComponentBasisPolicy p;
        // Captured declarations retain their engineering evidence. __LINE__ is
        // a diagnostic location only; audit_component_basis verifies live IR.
#define DECL(name, value, unit, basis, klass, numeric) \
        p.declarations.push_back({name, value, unit, basis, klass, numeric, \
            "native/src/component_basis_registry.cpp:" + std::to_string(__LINE__)})
        DECL("subsystems.CAMERA_LANE_TERM", "100R", "ohm", "Xilinx XAPP894 '7-series + external passives' D-PHY topology: an HR bank cannot switch DIFF_TERM, so each CSI-2 pair carries a fixed external 100 ohm differential termination at the receiver end of the trace.", "datasheet", false);
        DECL("subsystems.CAMERA_I2C_PULL", "4k7", "ohm", "MIPI CCI / I2C Rp on the gated +VDD_CAM rail. NXP UM10204 eq 2 gives Rp(max) = tr / (0.8473 * Cb); at Fast-mode 400 kHz (tr 300 ns) 4k7 holds for Cb <= 75 pF, which the short FFC control pair meets. House value shared with the lcd touch bus; the bus is dead without it (open drain).", "policy", false);
        DECL("subsystems.CAMERA_RAIL_BYPASS", "100n", "F", "HF bypass at the FFC power pin (J1.15) on the gated camera rail.", "policy", false);
        DECL("subsystems.CAMERA_RAIL_BULK", "10u", "F", "Local bulk at the FFC for the RPi V2/IMX219 ~250 mA module budget; the peer FFC subsystems (lcd, microsd) carry the same 10u at the connector.", "policy", false);
        DECL("subsystems.ETHERNET_BOB_SMITH_R", "75R", "ohm", "IEEE 802.3 section 40.7.1 Bob-Smith HF termination: each MEDIA centre tap sees 75 ohm (half the 150 ohm common-mode impedance of a UTP pair) into the shared trunk. LCSC C4275.", "datasheet", false);
        DECL("subsystems.ETHERNET_BOB_SMITH_C", "1n", "F", "Bob-Smith trunk cap and the single BS_COMMON -> CHASSIS_GND isolation element. GENUINE 1 nF / 2 kV X7R (IEC 60950/62368 hi-pot), 1206 body for the 2 kV rating; LCSC C9196 (FH 1206B102K202NT), JLC Basic.", "datasheet", false);
        DECL("subsystems.HDMI_RX_HPD_ASSERT", "1k", "ohm", "HDMI 1.4 section 4.2.6 passive hot-plug assert: the cable's own +5V (pin 18) is returned to HPD (pin 19) through 1 kohm, so a plugged source sees HPD high and reads EDID with the consuming board unpowered.", "datasheet", false);
        DECL("subsystems.HDMI_RX_CEC_PULL", "27k", "ohm", "HDMI 1.4 CEC Supplement 1: the CEC line carries a 27 kohm pull-up to the device's 3.3 V supply. Here the gated module rail +VDD_LOGIC.", "datasheet", false);
        DECL("subsystems.HDMI_RX_DET_TOP", "10k", "ohm", "Cable-5V presence divider, top leg. With the 15k bottom leg the worst-case cable rail 5.25 V presents 5.25*15/25 = 3.15 V at HDMI_5V_DET — inside LVCMOS33 abs-max, so the detect line is safe on a 3.3 V bank.", "datasheet", false);
        DECL("subsystems.HDMI_RX_DET_BOTTOM", "15k", "ohm", "Cable-5V presence divider, bottom leg; the 10k/15k ratio sets the 3.15 V worst-case output (see HDMI_RX_DET_TOP).", "datasheet", false);
        DECL("subsystems.HDMI_RX_EDID_BYPASS", "100n", "F", "M24C02 EDID EEPROM VCC bypass on the cable-5V quasi-rail.", "policy", false);
        DECL("subsystems.HDMI_TX_RAIL_BYPASS", "100n", "F", "TI TPD12S016 SLLSE96F Figure 15: 100 nF on V_CCA (pin 24) and on V_CC5V (pin 11).", "datasheet", false);
        DECL("subsystems.HDMI_TX_RAIL_BULK", "10u", "F", "Module bulk on the +VDD_IO controller rail; the peer connector subsystems (camera, microsd) carry the same 10u per module rail.", "policy", false);
        DECL("subsystems.HDMI_TX_CABLE_BYPASS", "100n", "F", "HDMI 1.4 section 4.2.7: HF decoupling on the source's switched +5V at the receptacle (pin 18).", "datasheet", false);
        DECL("subsystems.HDMI_TX_CABLE_BULK", "1u", "F", "HDMI 1.4 section 4.2.7 bulk companion to the 100 nF at the receptacle +5V pin.", "datasheet", false);
        DECL("subsystems.HDMI_TX_STRAP_PULL", "10k", "ohm", "TI TPD12S016 SLLSE96F Figure 15 / section 8.2.1 'HDMI source using one GPIO': LS_OE (pin 5) and CT_HPD (pin 12) strapped HIGH through 10 kohm to V_CCA so the level shifters and the 55 mA +5V switch are always on.", "datasheet", false);
        DECL("subsystems.LCD_ISET_SENSE", "1.5R", "ohm", "Silergy SY7201 WLED-boost current set: I_LED = V_FB / R_ISET with V_FB = 0.2 V, so 0.2/1.5 = 133 mA into the LED string.", "datasheet", false);
        DECL("subsystems.LCD_BOOST_INDUCTOR", "10uH", "H", "SY7201 application inductor (SWPA4030S100MT, 10 uH).", "datasheet", false);
        DECL("subsystems.LCD_BOOST_CIN", "10u", "F", "SY7201 boost input bulk per the application circuit (10u + 1u at IN).", "datasheet", false);
        DECL("subsystems.LCD_BOOST_HF", "1u", "F", "SY7201 dedicated HF ceramic at the IN pin; the application circuit specifies 10u + 1u and only the 10u was fitted (audit 2026-06-20).", "datasheet", false);
        DECL("subsystems.LCD_BOOST_COUT", "2.2u", "F", "SY7201 boost output cap on LCD_VLED_P, 50 V X7R (LCSC C125847). The node resolves to the 30 V open-LED OVP clamp; continuous string voltage is ~9.6 V, so the 50 V part carries the rare fault transient with the 2x MLCC derate applied to the continuous bias (LCD-1).", "datasheet", false);
        DECL("subsystems.LCD_PANEL_BYPASS", "100n", "F", "Panel VDD HF bypass at the FFC on the gated +VDD_LCD rail (lcd_backlight.md 3.1: '10uF + 100n').", "datasheet", false);
        DECL("subsystems.LCD_PANEL_BULK", "10u", "F", "Panel VDD bulk (lcd_backlight.md 3.1: '10uF + 100n'); only the 100n was present, the peers camera/microsd carry 10u.", "datasheet", false);
        DECL("subsystems.LCD_TOUCH_PULL", "4k7", "ohm", "Capacitive-touch I2C Rp to the gated +VDD_LCD. NXP UM10204 eq 2 gives Rp(max) = tr / (0.8473 * Cb); at Fast-mode 400 kHz (tr 300 ns) 4k7 holds for Cb <= 75 pF. Open-drain bus: without these the bus is dead.", "policy", false);
        DECL("subsystems.LCD_RESET_PULLDOWN", "100k", "ohm", "Touch-controller reset held asserted until the host releases it — a driven reset, not an RC reset, so no cap-to-GND by design.", "policy", false);
        DECL("subsystems.LCD_DISP_PULLUP", "10k", "ohm", "Panel display-enable defaults ON whenever the gated rail is up.", "policy", false);
        DECL("subsystems.LCD_PCLK_DAMPING", "22R", "ohm", "Source-series damping on the ~33 MHz pixel clock, the highest-edge-rate line on the FFC; the resistor sits at the host/source end so the series sum approaches the ~50 ohm trace impedance.", "policy", false);
        DECL("subsystems.LCD_BLPWM_PULLDOWN", "100k", "ohm", "SY7201 EN/PWM held low so the backlight boost is OFF until the host drives it high.", "policy", false);
        DECL("subsystems.MICROSD_CARD_PULL", "100k", "ohm", "TI SCEA054A: the TXS02612 B0 one-shot outputs already hold an internal pull-up (4 kohm high / 40 kohm low, fig.1). An external pull parallels the internal 40 kohm while driving low — Table 1 measures VOL 29 mV (no pull) -> 169 mV (~10k) -> 38 mV (100k), guidance '>50 kohm beneficial'. 100k keeps an SD-spec anti-float pull inside that band. LCSC C25803.", "datasheet", false);
        DECL("subsystems.MICROSD_DETECT_PULL", "10k", "ohm", "Card-detect pull-up. NOT on a TXS02612 output, so the SCEA054A >50 kohm rule does not apply and the plain 10k anti-float value stands.", "policy", false);
        DECL("subsystems.MICROSD_HOST_BYPASS", "100n", "F", "TXS02612 VCCA (host-side) local bypass.", "policy", false);
        DECL("subsystems.MICROSD_CARD_BYPASS", "100n", "F", "Card-rail HF bypass (VCCB0/VCCB1 + slot VDD).", "policy", false);
        DECL("subsystems.MICROSD_CARD_BULK", "22u", "F", "Card-rail bulk sized for SD write bursts: the SD physical spec allows ~200 mA on the card supply, and the budgeted draw is 250 mA.", "datasheet", false);
        DECL("subsystems.MICROSD_ESD_BYPASS", "100n", "F", "TI SLLS546: the TPD6E001 VCC sets the clamp reference; a floating VCC gives the worst-case clamp, so VCC is biased to the card rail and bypassed locally (SD-1).", "datasheet", false);
        DECL("subsystems.PD_INPUT_INLET_BYPASS", "100n", "F", "TPS26631 datasheet-minimum input capacitance at the raw receptacle VBUS, alongside the SMBJ22A TVS.", "datasheet", false);
        DECL("subsystems.PD_INPUT_OVP_TOP", "100k", "ohm", "TPS26631 OVP divider, top leg from +VBUS_CONN. With the 5.49k bottom leg the OVP trip is 23.06 V typ — above the 21 V worst-case 20 V PD contract and below the downstream 24 V-class limits (PD-1 widened the window).", "datasheet", false);
        DECL("subsystems.PD_INPUT_OVP_BOTTOM", "5.49k", "ohm", "TPS26631 OVP divider, bottom leg; the 100k/5.49k ratio sets the 23.06 V typ trip (PD-1). LCSC C188263.", "datasheet", false);
        DECL("subsystems.PD_INPUT_ILIM_SET", "5.1k", "ohm", "TPS26631 current limit: I_OL = 18 / R_ILIM(kohm) = 18/5.1 = 3.5 A, above the 3 A PD contract with margin.", "datasheet", false);
        DECL("subsystems.PD_INPUT_DVDT_CAP", "47n", "F", "TPS26631 dVdT soft-start cap; 47 nF sets a 1.02 V/ms output slew, so the downstream bulk charges without tripping the current limit.", "datasheet", false);
        DECL("subsystems.PD_INPUT_FAULT_PULL", "100k", "ohm", "Open-drain FLT# pull-up to the always-on +VDD_LOGIC (never the 20 V inlet VBUS — an expander IO abs-max is far below the PD contract).", "policy", false);
        DECL("subsystems.PD_INPUT_FUSED_BULK", "10u", "F", "The dVdT-charged board bulk behind the eFuse; 1210 50 V X7R (LCSC C596319) for the 21 V worst-case rail.", "datasheet", false);
        DECL("subsystems.PMOD_SERIES_DAMPING", "200R", "ohm", "Digilent Pmod specification: each host IO carries a 200 ohm series protection resistor between the host signal and the socket pin. LCSC C8218.", "datasheet", false);
        DECL("subsystems.PMOD_RAIL_BYPASS", "100n", "F", "Per-port HF bypass at the Pmod VCC pins (positions 6/12).", "policy", false);
        DECL("subsystems.PMOD_RAIL_BULK", "10u", "F", "Per-port bulk for the Digilent ~100 mA per-module budget.", "policy", false);
        DECL("subsystems.PMOD_EXP_ILIM_SET", "13k", "ohm", "Silergy SY6280 current limit: I_LIM = 6800 / R_ISET(kohm) = 6800/13 = 523 mA, above the Digilent ~100 mA per-module budget with margin. LCSC C22797.", "datasheet", false);
        DECL("subsystems.PMOD_EXP_INPUT_BYPASS", "100n", "F", "HF bypass at the SY6280 IN pin, ahead of the 10u input bulk.", "policy", false);
        DECL("subsystems.PMOD_EXP_INPUT_BULK", "10u", "F", "SY6280 datasheet Pin Description ('IN ... decoupled with a 10uF capacitor to GND') and Application Information ('a 10uF ceramic capacitor from VIN to GND is strongly recommended'): without it an output short rings the input, and the rail bulk sits upstream of the inlet shunt.", "datasheet", false);
        DECL("subsystems.PMOD_EXP_OUTPUT_BYPASS", "100n", "F", "SY6280 OUT-pin HF bypass; the datasheet 10u OUT bulk is met by the socket bulk on the same +VSW_PMOD net.", "datasheet", false);
        DECL("subsystems.PMOD_EXP_ENABLE_PULLDOWN", "100k", "ohm", "Holds SY6280 EN low so the port is dark at power-up until the DSHP04 switch is closed by hand — a peripheral cannot be back-fed.", "policy", false);
        DECL("subsystems.PMOD_EXP_LED_SERIES", "330R", "ohm", "Status LED on the gated 3.3 V output: (3.3 - 2.0)/330 = 3.9 mA through the KT-0603R red LED.", "policy", false);
        DECL("subsystems.PMOD_EXP_SOCKET_BYPASS", "100n", "F", "HF bypass at the Pmod VCC pins (positions 6/12).", "policy", false);
        DECL("subsystems.PMOD_EXP_SOCKET_BULK", "10u", "F", "Socket bulk for the Digilent ~100 mA module budget; also serves as the SY6280 OUT bulk (same net).", "datasheet", false);
        DECL("subsystems.POWER_VIN_HF", "100n", "F", "TI SNVSBD5D 9.2.2.5 requires a 100 nF at EACH VIN/PGND pin pair immediately adjacent to the LM61460, rated 50 V with X7R or better. LCSC C14663 (CC0603KRX7R9BB104, 100 nF 50 V X7R) meets the rule; the VQFN-HR splits VIN/PGND across opposite package sides so one goes at each.", "datasheet", false);
        DECL("subsystems.POWER_VIN_BULK", "10u", "F", "SNVSBD5D 9.2.2.5 '>=10 uF ceramic at the input'; 2x 1206 50 V-class for the 21 V +VIN rail.", "datasheet", false);
        DECL("subsystems.POWER_5V_BULK", "22u", "F", "Input bulk for the +3V3 buck off the board +5V rail (SNVSBD5D 9.2.2.5); 0805 25 V-class, 2 pieces.", "datasheet", false);
        DECL("subsystems.POWER_VCC_BYPASS", "1u", "F", "SNVSBD5D 9.2.2.8: 1 uF from VCC (pin 2) to AGND, the internal-LDO bypass, 16 V ceramic.", "datasheet", false);
        DECL("subsystems.POWER_BIAS_SERIES", "10R", "ohm", "SNVSBD5D 9.2.2.9: 'a series resistor, 1 ohm to 10 ohm, can be added between VOUT and BIAS'. Top of the band for maximum noise filtering; the BIAS LDO sink current is small so the IR drop is negligible. LCSC C22859.", "datasheet", false);
        DECL("subsystems.POWER_BIAS_BYPASS", "1u", "F", "SNVSBD5D 9.2.2.9: 'a bypass capacitor of 1 uF or higher can be added close to the BIAS pin'.", "datasheet", false);
        DECL("subsystems.POWER_RT_FREQ", "22k", "ohm", "SNVSBD5D Eq 2: R_RT(kohm) = (1/fSW(kHz) - 3.3e-5) * 1.346e4, so 600 kHz gives 21.99k ~= 22.0k. 600 kHz keeps the existing 10 uH SWPA8040S within its 4 A Isat on both stages. LCSC C31850.", "datasheet", false);
        DECL("subsystems.POWER_BOOT_CAP", "100n", "F", "SNVSBD5D 9.2.2.6: 100 nF SW->CBOOT, X7R >=10 V. 9.2.2.7 allows RBOOT shorted to CBOOT, so pins 13/14 are one node and no boot resistor exists.", "datasheet", false);
        DECL("subsystems.POWER_SW_INDUCTOR", "10uH", "H", "SNVSBD5D 9.2.2.3 Eq 11 minimum at D<50% is L >= 0.2*Vout/fSW = 0.2*5/600k = 1.67 uH; 10 uH is well above it so the loop is stable with no subharmonic oscillation. Ripple dIL = 0.63 A p-p at 5 V (Ipk 3.27 A) and 0.187 A p-p at 3.3 V (Ipk 2.84 A), both under the 4 A Isat of the SWPA8040S (LCSC C37429).", "datasheet", false);
        DECL("subsystems.POWER_COUT_BULK", "22u", "F", "SNVSBD5D Table 9-5 (5 V application BOM) and Table 9-3 both list 3x 22 uF COUT at 5 V; 9.2.2.3 notes a larger-than-minimum inductor needs MORE output capacitance for transients, which the 10 uH choice makes the dominant term. 25 V Basic 0805, LCSC C45783.", "datasheet", false);
        DECL("subsystems.POWER_FB5V_TOP", "40.2k", "ohm", "SNVSBD5D 8.3.11 Vref = 1.0 V, Vout = 1.0*(1 + Rtop/Rbot): 40.2k/10k -> 5.02 V. LCSC C12447 (UNI-ROYAL 0603WAF4022T5E, 40.2k 0603 1%). BOM-CRITICAL: the prior C25750 was a mis-key resolving to a 120k 0402, which would set ~13.1 V on the +5V rail.", "datasheet", false);
        DECL("subsystems.POWER_FB3V3_TOP", "23.2k", "ohm", "SNVSBD5D 8.3.11 Vref = 1.0 V: 23.2k/10k -> 3.32 V, worst case ~[3.24, 3.40], centred in the +-3% window [3.201, 3.399]. Replaced 22.1k, whose 3.21 V nominal left only ~3.13 V against the 3.135 V floor. LCSC C23346.", "datasheet", false);
        DECL("subsystems.POWER_FB_BOTTOM", "10k", "ohm", "Common FB-divider bottom leg for both LM61460 stages; the ratio against the per-stage top leg sets Vout (SNVSBD5D 8.3.11). LCSC C25804.", "datasheet", false);
        DECL("subsystems.POWER_CFF_CAP", "22p", "F", "SNVSBD5D 9.2.2.10 feedforward across the FB-top resistor for phase margin with low-ESR ceramic COUT. Tables 9-2 and 9-5 both list CFF = 22 pF at 5 V. The ESR zero of a ceramic COUT is well above the 200 kHz no-CFF threshold, and both Vout are below the 14 V no-CFF ceiling.", "datasheet", false);
        DECL("subsystems.POWER_RFF_SERIES", "1k", "ohm", "SNVSBD5D 9.2.2.10: 'a 1-kohm resistor, RFF, can be placed in series with CFF' because CFF conducts output noise straight to FB. Table 9-2 5 V row lists RFF = 1 kohm.", "datasheet", false);
        DECL("subsystems.POWER_LED5V_SERIES", "1k", "ohm", "Rail-up indicator on the 5 V regulator-side node: (5.0 - 2.0)/1000 = 3.0 mA through the red LED.", "policy", false);
        DECL("subsystems.POWER_LED_SERIES", "330R", "ohm", "Rail-up indicator on the 3.3 V-class nodes: (3.3 - 2.0)/330 = 3.9 mA through the red LED.", "policy", false);
        DECL("subsystems.POWER_LDO_CAP", "1u", "F", "AP2112K input and output capacitance: the datasheet requires >=1 uF on both, and the LDO is stable with a 1 uF ceramic output cap.", "datasheet", false);
        DECL("subsystems.POWER_GATE_STOP", "1k", "ohm", "AO3400A gate-stop for the +1V8 PG sense cell. PWR-6: with the 100k pulldown a 10k series made Vgs = 1.8*100/110 = 1.64 V, barely over the 1.45 V max Vgs(th); 1k gives 1.8*100/101 = 1.78 V and is a pure RC gate-stop rather than a divider.", "measured", false);
        DECL("subsystems.POWER_GATE_PULLDOWN", "100k", "ohm", "AO3400A gate pulldown holding the +1V8 sense FET off until the rail is up; sets the divider ratio in PWR-6 above.", "policy", false);
        DECL("subsystems.RJ45_LED_SERIES", "330R", "ohm", "The two LEDs integrated in the KH-5224 housing driven as a steady port-present indicator off the always-on +VLED: (3.3 - 2.0)/330 = 4 mA each. LCSC C23138.", "policy", false);
        DECL("subsystems.UART_BRIDGE_SUPPLY_BYPASS", "100n", "F", "SiLabs CP2102N self-powered reference: 100 nF on each of VREGIN (pin 7), VDD (pin 6) and VIO (pin 5).", "datasheet", false);
        DECL("subsystems.UART_BRIDGE_VREGIN_BULK", "10u", "F", "CP2102N self-powered reference bulk on VREGIN alongside the 100 nF.", "datasheet", false);
        DECL("subsystems.UART_BRIDGE_RESET_PULL", "1k", "ohm", "CP2102N ~RST is open-drain and needs an external pull to VDD33; the part carries its own internal POR so no RC cap is fitted.", "datasheet", false);
        DECL("subsystems.UART_BRIDGE_SENSE_TOP", "22k1", "ohm", "CP2102N self-powered VBUS-sense divider, top leg from the UART receptacle's own 5 V VBUS. With the 47k5 bottom leg the pin sees 5*47.5/69.6 = 3.41 V, inside the 5.8 V abs-max. LCSC C25961.", "datasheet", false);
        DECL("subsystems.UART_BRIDGE_SENSE_BOTTOM", "47k5", "ohm", "CP2102N VBUS-sense divider, bottom leg (see UART_BRIDGE_SENSE_TOP). LCSC C23061.", "datasheet", false);
        DECL("subsystems.JTAG_LDO_CIN", "1u", "F", "AP2112K input capacitance for the self-powered island LDO (datasheet minimum 1 uF).", "datasheet", false);
        DECL("subsystems.JTAG_LDO_COUT", "10u", "F", "AP2112K output bulk; the datasheet minimum is 1 uF and 10 uF carries the CH347 + buffer + pull network on the island rail.", "datasheet", false);
        DECL("subsystems.JTAG_SUPPLY_BYPASS", "100n", "F", "CH347 datasheet section 5.1 (~0.1 uF on VCC), plus the same HF bypass on the SN74LVC125 VCC and the island LDO output.", "datasheet", false);
        DECL("subsystems.JTAG_CRYSTAL_FREQ", "8MHz", "Hz", "CH347 datasheet section 5.1 clock: 8 MHz crystal on XI/XO (KDS 1C208000BC0R, LCSC C57131).", "datasheet", false);
        DECL("subsystems.JTAG_CRYSTAL_LOAD", "16p", "F", "The CH347 datasheet 5.1 '~22 pF' is boilerplate for a CL=20 pF crystal. The fitted 1C208000BC0R is cut for CL=12 pF, so Cext = 2*(CL - Cstray) = 2*(12 - ~4) = 16 pF C0G per leg; 22 pF would over-load it and pull 8 MHz slow. LCSC C162205.", "datasheet", false);
        DECL("subsystems.JTAG_RESET_PULL", "10k", "ohm", "CH347 RST# (pin 1) already carries an internal pull-up and a built-in power-on reset (DS 5.1); the external 10k is noise-immunity insurance and no RC cap is fitted.", "datasheet", false);
        DECL("subsystems.JTAG_MODE_PULLDOWN", "10k", "ohm", "CH347 DS section 5.2 mode table: MODE 3 (JTAG + UART) needs DTR1 (pin 10) and RTS1 (pin 13) both pulled LOW at power-on reset. Both pins carry built-in pull-ups of ~40 kohm, so a 10k external pulldown dominates.", "datasheet", false);
        DECL("subsystems.JTAG_OE_PULLUP", "100k", "ohm", "Default-OFF isolation: all four SN74LVC125 OE# pins are held HIGH (outputs Hi-Z) through 100k to the island rail until SW1 pulls them to GND, so a pod on the target JTAG header never contends with the bridge.", "policy", false);
        DECL("subsystems.JTAG_CONN_VBUS_BULK", "10u", "F", "USB-C UFP VBUS bulk/bypass at the receptacle; the board-standard 0805 25 V part (LCSC C15850).", "policy", false);
        DECL("subsystems.JTAG_CONN_CC_RD", "5.1k", "ohm", "USB Type-C specification device/UFP role: one Rd = 5.1 kohm +-20% per CC pin to GND, which tells a source to apply VBUS. LCSC C23186 is a 5% Basic part, inside the +-20% spec.", "datasheet", false);
        DECL("subsystems.USB_PD_VDD_BYPASS", "100n", "F", "onsemi FUSB302B reference circuit: 100 nF HF on VDD.", "datasheet", false);
        DECL("subsystems.USB_PD_VDD_BULK", "10u", "F", "FUSB302B reference circuit: 10 uF bulk companion on VDD.", "datasheet", false);
        DECL("subsystems.USB_PD_VBUS_BYPASS", "100n", "F", "FUSB302B reference circuit: 100 nF on the VBUS-sense pin (U1.2), whose abs-max is 28 V.", "datasheet", false);
        DECL("subsystems.USB_PD_CC_FILTER", "200p", "F", "FUSB302B reference circuit: 200 pF analog filter from each CC line to GND. NP0 0603 (LCSC C113796) so the BMC edge is not distorted by dielectric loss.", "datasheet", false);
        DECL("subsystems.UART_CONN_VBUS_BULK", "10u", "F", "USB-C UFP VBUS decoupling (Cbus) at the receptacle; the board-standard 0805 25 V part (LCSC C15850) against the 5.25 V worst-case rail.", "datasheet", false);
        DECL("subsystems.UART_CONN_CC_RD", "5.1k", "ohm", "USB Type-C specification device/UFP role: one Rd = 5.1 kohm +-20% per CC pin; a source's Rp plus this Rd forms the attach divider. LCSC C23186 (0603WAF5101T5E, 5% Basic) is inside the spec tolerance.", "datasheet", false);
        DECL("subsystems.OTG_INPUT_BYPASS", "100n", "F", "TI TPS2051C input bypass at the switch IN pin.", "datasheet", false);
        DECL("subsystems.OTG_VBUS_MLCC", "22u", "F", "HF companion on the sourced VBUS. MLCC alone is not enough: at 5 V bias it derates to ~15-20 uF, below the USB 2.0 host-port 120 uF minimum and the TPS2051C datasheet 150 uF reference, so the bulk is carried by the electrolytic instead (more MLCC would only re-derate).", "datasheet", false);
        DECL("subsystems.OTG_VBUS_BULK", "100u", "F", "DMBJ RVT1C101M0605 100 uF 16 V aluminium electrolytic (LCSC C970684): its capacitance does NOT bias-derate, so it holds VBUS above 4.4 V through a device hot-plug. Pad 1 = +, pad 2 = -.", "datasheet", false);
        DECL("subsystems.OTG_ENABLE_PULLDOWN", "100k", "ohm", "TPS2051C EN is active-high; the pulldown holds the host VBUS switch OFF until the host drives VBUS_EN, so the port cannot source 5 V at power-on before the OTG role is decided.", "policy", false);
        DECL("subsystems.OTG_FAULT_PULLUP", "100k", "ohm", "TPS2051C FLT# is open-drain; the pull-up rails to +VDD_LOGIC so the flag stays inside the reader's IO abs-max and remains readable when the +VBUS_SUPPLY module rail is gated off.", "policy", false);
        DECL("subsystems.OTG_CC_RP", "56k", "ohm", "USB Type-C specification host/DFP role: Rp = 56 kohm +-20% per CC pin to VBUS advertises Default USB power. LCSC C23206 (0603WAF5602T5E, 1%).", "datasheet", false);
        DECL("subsystems.OTG_ID_STRAP", "1k", "ohm", "OTG ID strapped to GND through 1 kohm = HOST role for this port; the series resistance limits current if a host drives the ID line.", "policy", false);
        DECL("carrier.board_aux.iset", "13k", "ohm", "SY6280 current limit ILIM = 6800/13k = 523 mA, over the 200 mA QWIIC budget. LCSC C22797.", "datasheet", false);
        DECL("carrier.board_aux.en_pulldown", "100k", "ohm", "Holds EN_AUX low so the gate is OFF at power-up until a human closes SW1 pos 1 (constraint C1). LCSC C25803.", "datasheet", false);
        DECL("carrier.board_aux.decap", "100n", "F", "SY6280 and PCA9306 per-pin bypass. LCSC C14663.", "datasheet", false);
        DECL("carrier.board_aux.out_bulk", "10u", "F", "Hold-up on the gated +3V3_AUX rail for the 200 mA QWIIC load. The SY6280 datasheet recommends an output cap and only the 100n was fitted (audit 2026-06-19); its soft-start tolerates 10u. 0805 25 V, LCSC C15850.", "datasheet", false);
        DECL("carrier.board_aux.led_ballast", "330R", "ohm", "KT-0603R status LED ballast, ~3.9 mA from +3V3_AUX. LCSC C23138.", "datasheet", false);
        DECL("carrier.board_aux.iso_en_pullup", "100k", "ohm", "Ties the PCA9306 EN to +3V3_AUX so the switch OPENS whenever the gated rail is down — that isolation is what stops the powered-down peripherals back-powering the always-on trunk through their ESD diodes (LAW 0). LCSC C25803.", "datasheet", false);
        DECL("carrier.board_aux.bus_pullup", "4k7", "ohm", "AUX-side I2C pulls to the gated rail; the PCA9306 requires pulls on BOTH sides. LCSC C23162.", "datasheet", false);
        DECL("carrier.board_aux.i2c_speed", "400000", "Hz", "Fast-mode on both sides of the isolator.", "datasheet", true);
        DECL("carrier.board_qwiic.i2c_speed", "400000", "Hz", "Fast-mode AUX_I2C.", "datasheet", true);
        DECL("carrier.board_services.i2c_speed", "400000", "Hz", "Fast-mode AUX_I2C, the PCA9306-isolated segment of STM32_I2C2.", "datasheet", true);
        DECL("carrier.board_services.decap", "100n", "F", "Per-IC supply bypass. LCSC C14663.", "datasheet", false);
        DECL("carrier.board_services.int_pullup", "10k", "ohm", "RV-3028 open-drain alarm pull to the gated rail. LCSC C25804.", "datasheet", false);
        DECL("carrier.board_services.wdi_series_r", "1k", "ohm", "Limits ESD back-feed into U3.WDI while +3V3_AUX is off but the PL still drives. It does NOT divide the kick: the LVCMOS33 driver VOH ~3.0 V clears the TPS3823 VIH = 0.7*VDD = 2.31 V, which the previous LVCMOS25 driver (VOH ~2.1 V) could not reliably meet. LCSC C21190.", "datasheet", false);
        DECL("carrier.bringup_en.dip_pulldown", "100k", "ohm", "A-input pulldown, so an OPEN DIP reads 0 and a closed DIP reads 1. LCSC C25803.", "datasheet", false);
        DECL("carrier.bringup_en.override_pullup", "100k", "ohm", "B-input pull to +3V3_SC, so a Hi-Z override source means ENABLED. That is what lets a blank system controller boot 'switches only'. LCSC C25803.", "datasheet", false);
        DECL("carrier.bringup_en.gate_decap", "100n", "F", "One bypass per gate on +3V3_SC. LCSC C14663.", "datasheet", false);
        DECL("carrier.bringup_en_modules.dip_pulldown", "100k", "ohm", "A-input pulldown, so an OPEN DIP reads 0 and a closed DIP reads 1. LCSC C25803.", "datasheet", false);
        DECL("carrier.bringup_en_modules.override_pullup", "100k", "ohm", "B-input pull to +3V3_SC so a Hi-Z TCA9535 port means ENABLED. The LCD_BL cell is the ONE exception: P10 carries a 100k pullDOWN on bringup_rails instead, so that provision defaults OFF until software raises it.", "datasheet", false);
        DECL("carrier.bringup_en_modules.gate_decap", "100n", "F", "One bypass per gate on +3V3_SC. LCSC C14663.", "datasheet", false);
        DECL("carrier.bringup_modules.iset_523ma", "13k", "ohm", "SY6280 ILIM = 6800/RSET, so 13k -> 523 mA for the lighter module rails. LCSC C22797.", "datasheet", false);
        DECL("carrier.bringup_modules.iset_1a", "6.8k", "ohm", "SY6280 ILIM = 6800/RSET, so 6.8k -> 1.0 A for the heavier rails (LCD, SD, USB, LCD_5V). LCSC C23212.", "datasheet", false);
        DECL("carrier.bringup_modules.led_r_3v3", "330R", "ohm", "Status LED on a 3.3 V gated rail: (3.3-2.0)/330R ~= 3.9 mA (dossier 3.3). LCSC C23138.", "datasheet", false);
        DECL("carrier.bringup_modules.led_r_5v", "1k", "ohm", "Status LED on a 5 V gated rail: (5-2)/1k = 3 mA (dossier 3.3). LCSC C21190.", "datasheet", false);
        DECL("carrier.bringup_modules.switch_decap", "100n", "F", "Local bypass on each SY6280 IN and OUT (dossier 3.2 wiring note). LCSC C14663.", "datasheet", false);
        DECL("carrier.bringup_modules.sd_bleed", "10k", "ohm", "ONLY the SD rail gets this. A microSD power-cycle re-init needs VDD below ~0.5 V, but the SY6280 has no quick-output-discharge, so +3V3_SD would decay only through a possibly-high-Z card and could strand above 0.5 V. 0.33 mA static is far under the 1 A limit and cannot mis-trip (research R5; audit 2026-06-20). LCSC C25804.", "datasheet", false);
        DECL("carrier.bringup_rails.i2c_speed", "400000", "Hz", "Fast-mode STM32_I2C2.", "datasheet", true);
        DECL("carrier.bringup_rails.bus_pullup", "4k7", "ohm", "The STM32_I2C2 pull-ups live ONCE, here, on +3V3_SC — dossier risk R1: the bus must be alive before any carrier rail exists, because PD negotiation precedes them all. LCSC C23162.", "datasheet", false);
        DECL("carrier.bringup_rails.int_pullup", "10k", "ohm", "This sheet OWNS the single pull-up for the merged SC_INT_N net (the TCA9535 INT# wire-ORed with the FUSB302 INT, G2). usb_pd's redundant 4k7 was deleted — one pull per net. LCSC C25804.", "datasheet", false);
        DECL("carrier.bringup_rails.spare_pulldown", "100k", "ohm", "The TCA9535 has NO internal pulls (unlike the PCA9555), so an unused port must not float. P10 also carries this pulldown so the LCD_BL provision defaults OFF until software raises it. LCSC C25803.", "datasheet", false);
        DECL("carrier.bringup_rails.button_pullup", "10k", "ohm", "Active-LOW PL buttons pulled to +3V3, the bank VCCO of those PL pins. LCSC C25804.", "datasheet", false);
        DECL("carrier.bringup_rails.debounce_cap", "100n", "F", "RC debounce across the tact contacts. LCSC C14663.", "datasheet", false);
        DECL("carrier.bringup_rails.expander_decap", "100n", "F", "TCA9535 VCC bypass. LCSC C14663.", "datasheet", false);
        DECL("carrier.bringup_rails.pudc_strap", "10k", "ohm", "IO_L3P_PUDC_34 has NO resistor on the SoM. PUDC LOW during config ENABLES the internal pull-ups (UG470), which suits the LCD 'DISP defaults on' 10k and the active-low PL buttons. The strap is a carrier-side part so it lives on this config-strap sheet, not the connector-only J3 sheet. LCSC C25804.", "datasheet", false);
        DECL("carrier.debug_boot.jtag_pullup", "4k7", "ohm", "Insurance pull-ups on TMS/TDI to +3V3 (= VCCO_0, the header VREF level), so the chain is defined with no pod attached. LCSC C23162.", "datasheet", false);
        DECL("carrier.debug_boot.boot0_series_r", "100R", "ohm", "DIP pos 1 drives STM32_BOOT0 high through 100R against the SoM's 1k5 pull-down, so closed + reset selects USB DFU. The 100R/1k5 ratio is what makes the strap win without fighting the module pull hard. LCSC C22775.", "datasheet", false);
        DECL("carrier.debug_boot.bootsel_pullup", "10k", "ohm", "Defined-high pull for the BOOTSEL request straps and the spare; closing the DIP pulls the line to GND. SC firmware decodes these and drives the on-module Zynq BMODE pins. LCSC C25804.", "datasheet", false);
        DECL("carrier.fmc.pair_impedance", "100", "ohm", "Each bank-35 pair stays typed as a 100R diff pair: the SoM->header PCB trace is still impedance-controlled. Only the header pads themselves are not — the nature of a 0.1 in breakout.", "policy", true);
        DECL("carrier.fmc.rail_bulk", "10u", "F", "+3V3 bulk shared with J1.1 and the LDO input. LCSC C15850.", "datasheet", false);
        DECL("carrier.fmc.rail_hf", "100n", "F", "+3V3 bypass at the header. LCSC C14663.", "datasheet", false);
        DECL("carrier.fmc.ldo_in", "1u", "F", "TLV75725 input cap at U1.IN (pin 1). LCSC C15849.", "datasheet", false);
        DECL("carrier.fmc.ldo_out", "10u", "F", "TLV75725 output cap at U1.OUT (pin 5). LCSC C15850.", "datasheet", false);
        DECL("carrier.fmc.header_vadj_hf", "100n", "F", "At-header +2V5_VADJ bypass, a connector-rail cap left to the packer. LCSC C14663.", "datasheet", false);
        DECL("carrier.hdmi_rx_term.term", "49.9R", "ohm", "One 50R-class sink termination per single-ended line, 8 total for the three data lanes + clock. A Zynq-7000 HR bank does NOT self-terminate TMDS_33 (DIFF_TERM is HP-bank / 2.5 V-only), so without this network HDMI RX simply does not work. YAGEO RC0603FR-0749R9L 1% (LCSC C114625) — the low DC error keeps the TMDS common mode centred.", "datasheet", false);
        DECL("carrier.hdmi_rx_term.avcc_hf", "100n", "F", "Bank-local HF bypass for AVCC (DEF-G), 50 V X7R. LCSC C14663.", "datasheet", false);
        DECL("carrier.hdmi_rx_term.avcc_reservoir", "1u", "F", "Charge reservoir for the 64 mA termination load swinging against AVCC, 50 V X5R. LCSC C15849. On this IC-less sheet both caps anchor as rail-decoupling columns, not an IC cluster.", "datasheet", false);
        DECL("carrier.motor_pwm.oe_pullup", "10k", "ohm", "FAIL-SAFE ARM: holds #OE high so the buffer outputs stay HiZ and emit no spurious ESC pulses until the PL explicitly drives #OE low. LCSC C25804.", "datasheet", false);
        DECL("carrier.motor_pwm.servo_iset", "13k", "ohm", "SY6280 ILIM = 6800/13k = 523 mA, protecting board +5V against a shorted servo lead. Only the servo POWER row is limited; the buffer runs off raw +5V so it is always alive, armed by #OE. LCSC C22797.", "datasheet", false);
        DECL("carrier.motor_pwm.switch_decap", "100n", "F", "HF companion to the SY6280's recommended input cap, and the HCT245 VCC bypass. LCSC C14663.", "datasheet", false);
        DECL("carrier.motor_pwm.servo_holdup", "10u", "F", "Servo-rail hold-up at U3.OUT, the SY6280-recommended output cap. LCSC C15850.", "datasheet", false);
        DECL("carrier.motor_sense.shunt", "10mR", "ohm", "In-line current-sense element, RLM12FTCMR010 1206. The rail splits at it: ESC_VRAIL_IN is the high side, ESC_VRAIL the load side the INA3221 also uses as its bus-voltage sense node.", "datasheet", false);
        DECL("carrier.motor_sense.i2c_speed", "400000", "Hz", "Fast-mode STM32_I2C2.", "datasheet", true);
        DECL("carrier.motor_sense.rail_hf", "100n", "F", "HF bypass on the pre-shunt ESC bus. LCSC C14663.", "datasheet", false);
        DECL("carrier.motor_sense.supply_hf", "100n", "F", "INA3221 VS bypass. LCSC C14663.", "datasheet", false);
        DECL("carrier.motor_sense.supply_bulk", "10u", "F", "Local +3V3_SC bulk. LCSC C15850.", "datasheet", false);
        DECL("carrier.motor_sense.fault_pullup", "10k", "ohm", "Defined-high pull for the open-drain CRITICAL over-current alert. LCSC C25804.", "datasheet", false);
        DECL("carrier.motor_sense.rail_bulk", "470uF/35V", "F", "Local energy store for the ESC commutation-current pulses that also stabilises the bus-V node U2 meters. 35 V covers a 4S rail with >1.5x margin; the input TVS clamps the hot-plug edge. Placed on the LOAD-side net, not the dense pre-shunt trunk. LCSC C976030 (DMBJ RVT1V471M1010, D10x10.2) seats on the stock D10x10.5 land pattern.", "datasheet", false);
        DECL("carrier.power_mon.shunt_3a", "10mR", "ohm", "Series shunt on the 3 A rails (+VIN, +5V, +3V3), sized from the PLAN rail budgets: 30 mV at 3 A, 4 mA LSB. Part RLM12FTCMR010, 1206.", "datasheet", false);
        DECL("carrier.power_mon.shunt_600ma", "20mR", "ohm", "Series shunt on the 600 mA +1V8 rail: 12 mV, 2 mA LSB. Part RLM12FTCMR020, 1206.", "datasheet", false);
        DECL("carrier.power_mon.supply_hf", "100n", "F", "Per-VS decoupling. LCSC C14663, Basic, 20.6M stock (2026-06-11).", "datasheet", false);
        DECL("carrier.power_mon.supply_bulk", "10u", "F", "Shared +3V3_SC bulk for both monitors. LCSC C15850.", "datasheet", false);
        DECL("carrier.power_mon.alert_pullup", "10k", "ohm", "Defined-high pull for the wire-ORed open-drain CRITICAL outputs. LCSC C25804.", "datasheet", false);
        DECL("carrier.power_mon.i2c_speed", "400000", "Hz", "Fast-mode I2C on the shared STM32_I2C2 trunk. Bus pull-ups live on usb_pd/bringup, never duplicated here.", "datasheet", true);
        DECL("carrier.power_som.en_series_r", "10k", "ohm", "PWR-1 EN clamp, series +VIN_SYS -> EN. At low VIN the zener is off and the 1.55 uA hysteresis through 10k is under 16 uV, so EN tracks VIN and the buck surely enables at the 4.75 V default-USB contract; at high VIN this resistor absorbs VIN - Vz. LCSC C25804.", "datasheet", false);
        DECL("carrier.power_som.input_bulk", "10u", "F", "SNVSBD5D 9.2.2.5 input bulk, 50 V-class 1206 for the 21 V worst-case +VIN_SYS rail. LCSC C13585.", "datasheet", false);
        DECL("carrier.power_som.input_hf", "100n", "F", "SNVSBD5D 9.2.2.5 MANDATORY per-VIN-pin HF cap — one at VIN1/PGND1 and one at VIN2/PGND2, not one shared. LCSC C14663.", "datasheet", false);
        DECL("carrier.power_som.vcc_bypass", "1u", "F", "VCC internal-LDO bypass (SNVSBD5D). LCSC C15849.", "datasheet", false);
        DECL("carrier.power_som.bias_series_r", "10R", "ohm", "SNVSBD5D 9.2.2.9 BIAS series element. BIAS is tied to VOUT because 4.65 V clears the 3.1 V BIAS-active threshold and sits far under the 16 V BIAS max; identical idiom to U1/U2. LCSC C22859.", "datasheet", false);
        DECL("carrier.power_som.bias_bypass", "1u", "F", "BIAS bypass (SNVSBD5D 9.2.2.9). LCSC C15849.", "datasheet", false);
        DECL("carrier.power_som.rt", "22k", "ohm", "SNVSBD5D Eq 2 -> fSW ~600 kHz, matching U1/U2. LCSC C31850.", "datasheet", false);
        DECL("carrier.power_som.boot_cap", "100n", "F", "CBOOT (SNVSBD5D). RBOOT(13) shorts to CBOOT(14) as one node — a 0R wire per the DS EC table, no resistor fitted. LCSC C14663.", "datasheet", false);
        DECL("carrier.power_som.inductor", "10uH", "H", "SWPA8040S100MT, Isat 4.1 A over the 2.004 A load. LCSC C37429.", "datasheet", false);
        DECL("carrier.power_som.output_bulk", "22u", "F", "+5V_SOM output bulk, 2 x 0805. LCSC C45783.", "datasheet", false);
        DECL("carrier.power_som.fb_top", "47.5k", "ohm", "FB divider top. LM61460 Vref = 1.0 V (SNVSBD5D 8.3.11), so Vout = 1.0*(1+Rtop/Rbot); 47.5k/13k -> 4.654 V nom, worst-case corner [4.582, 4.728] V, inside the SoM 4.2-5.0 V input window (PWR-5 re-centred BELOW 5 V). LCSC C23061.", "datasheet", false);
        DECL("carrier.power_som.fb_bottom", "13k", "ohm", "FB divider bottom — see power_som.fb_top for the derivation. LCSC C22797.", "datasheet", false);
        DECL("carrier.power_som.ff_cap", "22p", "F", "CFF across the FB top (SNVSBD5D 9.2.2.10). LCSC C1653.", "datasheet", false);
        DECL("carrier.power_som.ff_series_r", "1k", "ohm", "RFF series damp for the feedforward cap (SNVSBD5D 9.2.2.10, applicable because VOUT 4.65 V < 14 V). LCSC C21190.", "datasheet", false);
        DECL("carrier.power_som.pg_led_r", "1k", "ohm", "KT-0603R power-good LED ballast, ~3 mA. LCSC C21190.", "datasheet", false);
        DECL("carrier.power_som.en_bypass", "100n", "F", "EN node bypass for the PWR-1 clamp. LCSC C14663.", "datasheet", false);
        DECL("carrier.som_decoupling.bulk", "22u", "F", "Charge reservoir at the DF40 power-pin entry, 25 V X5R 0805 (LCSC C45783), reusing a carrier-stocked ratings-verified MLCC.", "datasheet", false);
        DECL("carrier.som_decoupling.hf", "100n", "F", "High-frequency bypass at the DF40 power-pin entry, 50 V X7R 0603 (LCSC C14663).", "datasheet", false);
        DECL("carrier.user_io.led_r_high_vf", "200R", "ohm", "Ballast for the three high-Vf colours (green C12624 / blue C2288 / white C2290, Vf ~3.1 V). The rail is only 3.3 V, so the drop across the ballast is 3.3 - Vf: on 1k they would draw (3.3-3.1)/1k = 0.2 mA and be invisible. 200R gives ~1 mA at the 3.1 V corner up to 3.5 mA at the white 2.6 V corner, never over the 5 mA LED rating. LCSC C8218 (audit io_misc-1).", "datasheet", false);
        DECL("carrier.user_io.led_r_red", "1k", "ohm", "Red (Vf ~1.8-2.4 V) has ~1.3 V of headroom, so 1k gives ~1.3 mA. LCSC C21190.", "datasheet", false);
        DECL("carrier.user_io.button_pullup", "10k", "ohm", "Pulls the active-low tacts to the UNGATED +3V3 (= the VCCO_13 level) so they read correctly whenever the PL is alive, independent of the LED rail gate. LCSC C25804.", "datasheet", false);
        DECL("carrier.user_io.led_rail_hf", "100n", "F", "Bypass on the gated LED rail. LCSC C14663.", "datasheet", false);
        DECL("devkit_mini.debug_boot.jtag_pullup", "4k7", "ohm", "Insurance pull-ups on TMS/TDI to +3V3 (= VCCO_0, the header VREF level), so the chain is defined with no pod attached. LCSC C23162.", "datasheet", false);
        DECL("devkit_mini.debug_boot.boot0_series_r", "100R", "ohm", "DIP pos 1 drives STM32_BOOT0 high through 100R against the SoM's 1k5 pull-down, so closed + reset selects USB DFU. The 100R/1k5 ratio is what makes the strap win without fighting the module pull hard. LCSC C22775.", "datasheet", false);
        DECL("devkit_mini.debug_boot.bootsel_pullup", "10k", "ohm", "Defined-high pull for the BOOTSEL request straps and the spare; closing the DIP pulls the line to GND. SC firmware decodes these and drives the on-module Zynq BMODE pins. LCSC C25804.", "datasheet", false);
        DECL("devkit_mini.debug_boot.i2c_speed", "400000", "Hz", "Fast-mode STM32_I2C2, shared with the two INA3221 monitors.", "datasheet", true);
        DECL("devkit_mini.debug_boot.i2c_pullup", "4k7", "ohm", "The devkit omits bringup_rails, so its SC debug sheet owns one pull-up per STM32_I2C2 line to always-on +3V3_SC, matching the carrier and the INA3221/STM32 supply domain. C23162, 0603 1%. About 0.70 mA per asserted line; at 400 kHz the 300 ns rise-time limit allows about 74 pF including resistor tolerance. Keep bus/probe stubs short and verify rise time at bring-up.", "datasheet", false);
        DECL("devkit_mini.power_mon.shunt_3a", "10mR", "ohm", "Series shunt on the 3 A rails (+VIN, +5V, +3V3), sized from the PLAN rail budgets: 30 mV at 3 A, 4 mA LSB. Part RLM12FTCMR010, 1206.", "datasheet", false);
        DECL("devkit_mini.power_mon.shunt_600ma", "20mR", "ohm", "Series shunt on the 600 mA +1V8 rail: 12 mV, 2 mA LSB. Part RLM12FTCMR020, 1206.", "datasheet", false);
        DECL("devkit_mini.power_mon.supply_hf", "100n", "F", "Per-VS decoupling. LCSC C14663, Basic, 20.6M stock (2026-06-11).", "datasheet", false);
        DECL("devkit_mini.power_mon.supply_bulk", "10u", "F", "Shared +3V3_SC bulk for both monitors. LCSC C15850.", "datasheet", false);
        DECL("devkit_mini.power_mon.alert_pullup", "10k", "ohm", "Defined-high pull for the wire-ORed open-drain CRITICAL outputs. LCSC C25804.", "datasheet", false);
        DECL("devkit_mini.power_mon.i2c_speed", "400000", "Hz", "Fast-mode I2C on the shared STM32_I2C2 trunk. This devkit omits the carrier's bringup_rails sheet, so debug_boot owns the bus pull-ups.", "datasheet", true);
        DECL("devkit_mini.power_som.en_series_r", "10k", "ohm", "PWR-1 EN clamp, series +VIN_SYS -> EN. At low VIN the zener is off and the 1.55 uA hysteresis through 10k is under 16 uV, so EN tracks VIN and the buck surely enables at the 4.75 V default-USB contract; at high VIN this resistor absorbs VIN - Vz. LCSC C25804.", "datasheet", false);
        DECL("devkit_mini.power_som.input_bulk", "10u", "F", "SNVSBD5D 9.2.2.5 input bulk, 50 V-class 1206 for the 21 V worst-case +VIN_SYS rail. LCSC C13585.", "datasheet", false);
        DECL("devkit_mini.power_som.input_hf", "100n", "F", "SNVSBD5D 9.2.2.5 MANDATORY per-VIN-pin HF cap — one at VIN1/PGND1 and one at VIN2/PGND2, not one shared. LCSC C14663.", "datasheet", false);
        DECL("devkit_mini.power_som.vcc_bypass", "1u", "F", "VCC internal-LDO bypass (SNVSBD5D). LCSC C15849.", "datasheet", false);
        DECL("devkit_mini.power_som.bias_series_r", "10R", "ohm", "SNVSBD5D 9.2.2.9 BIAS series element. BIAS is tied to VOUT because 4.65 V clears the 3.1 V BIAS-active threshold and sits far under the 16 V BIAS max; identical idiom to U1/U2. LCSC C22859.", "datasheet", false);
        DECL("devkit_mini.power_som.bias_bypass", "1u", "F", "BIAS bypass (SNVSBD5D 9.2.2.9). LCSC C15849.", "datasheet", false);
        DECL("devkit_mini.power_som.rt", "22k", "ohm", "SNVSBD5D Eq 2 -> fSW ~600 kHz, matching U1/U2. LCSC C31850.", "datasheet", false);
        DECL("devkit_mini.power_som.boot_cap", "100n", "F", "CBOOT (SNVSBD5D). RBOOT(13) shorts to CBOOT(14) as one node — a 0R wire per the DS EC table, no resistor fitted. LCSC C14663.", "datasheet", false);
        DECL("devkit_mini.power_som.inductor", "10uH", "H", "SWPA8040S100MT, Isat 4.1 A over the 2.004 A load. LCSC C37429.", "datasheet", false);
        DECL("devkit_mini.power_som.output_bulk", "22u", "F", "+5V_SOM output bulk, 2 x 0805. LCSC C45783.", "datasheet", false);
        DECL("devkit_mini.power_som.fb_top", "47.5k", "ohm", "FB divider top. LM61460 Vref = 1.0 V (SNVSBD5D 8.3.11), so Vout = 1.0*(1+Rtop/Rbot); 47.5k/13k -> 4.654 V nom, worst-case corner [4.582, 4.728] V, inside the SoM 4.2-5.0 V input window (PWR-5 re-centred BELOW 5 V). LCSC C23061.", "datasheet", false);
        DECL("devkit_mini.power_som.fb_bottom", "13k", "ohm", "FB divider bottom — see power_som.fb_top for the derivation. LCSC C22797.", "datasheet", false);
        DECL("devkit_mini.power_som.ff_cap", "22p", "F", "CFF across the FB top (SNVSBD5D 9.2.2.10). LCSC C1653.", "datasheet", false);
        DECL("devkit_mini.power_som.ff_series_r", "1k", "ohm", "RFF series damp for the feedforward cap (SNVSBD5D 9.2.2.10, applicable because VOUT 4.65 V < 14 V). LCSC C21190.", "datasheet", false);
        DECL("devkit_mini.power_som.pg_led_r", "1k", "ohm", "KT-0603R power-good LED ballast, ~3 mA. LCSC C21190.", "datasheet", false);
        DECL("devkit_mini.power_som.en_bypass", "100n", "F", "EN node bypass for the PWR-1 clamp. LCSC C14663.", "datasheet", false);
        DECL("devkit_mini.som_decoupling.bulk", "22u", "F", "Charge reservoir at the DF40 power-pin entry, 25 V X5R 0805 (LCSC C45783), reusing a carrier-stocked ratings-verified MLCC.", "datasheet", false);
        DECL("devkit_mini.som_decoupling.hf", "100n", "F", "High-frequency bypass at the DF40 power-pin entry, 50 V X7R 0603 (LCSC C14663).", "datasheet", false);
#undef DECL
        p.uses = {
            {"library", "camera", "R1", "value", "subsystems.CAMERA_LANE_TERM", "Device:R"},
            {"library", "camera", "R2", "value", "subsystems.CAMERA_LANE_TERM", "Device:R"},
            {"library", "camera", "R3", "value", "subsystems.CAMERA_LANE_TERM", "Device:R"},
            {"library", "camera", "R4", "value", "subsystems.CAMERA_I2C_PULL", "Device:R"},
            {"library", "camera", "R5", "value", "subsystems.CAMERA_I2C_PULL", "Device:R"},
            {"library", "camera", "C1", "value", "subsystems.CAMERA_RAIL_BYPASS", "Device:C"},
            {"library", "camera", "C2", "value", "subsystems.CAMERA_RAIL_BULK", "Device:C"},
            {"library", "ethernet", "R1", "value", "subsystems.ETHERNET_BOB_SMITH_R", "Device:R"},
            {"library", "ethernet", "C1", "value", "subsystems.ETHERNET_BOB_SMITH_C", "Device:C"},
            {"library", "ethernet", "R2", "value", "subsystems.ETHERNET_BOB_SMITH_R", "Device:R"},
            {"library", "ethernet", "C2", "value", "subsystems.ETHERNET_BOB_SMITH_C", "Device:C"},
            {"library", "ethernet", "R3", "value", "subsystems.ETHERNET_BOB_SMITH_R", "Device:R"},
            {"library", "ethernet", "C3", "value", "subsystems.ETHERNET_BOB_SMITH_C", "Device:C"},
            {"library", "ethernet", "R4", "value", "subsystems.ETHERNET_BOB_SMITH_R", "Device:R"},
            {"library", "ethernet", "C4", "value", "subsystems.ETHERNET_BOB_SMITH_C", "Device:C"},
            {"library", "ethernet", "C5", "value", "subsystems.ETHERNET_BOB_SMITH_C", "Device:C"},
            {"library", "hdmi_rx", "R1", "value", "subsystems.HDMI_RX_HPD_ASSERT", "Device:R"},
            {"library", "hdmi_rx", "R2", "value", "subsystems.HDMI_RX_CEC_PULL", "Device:R"},
            {"library", "hdmi_rx", "R3", "value", "subsystems.HDMI_RX_DET_TOP", "Device:R"},
            {"library", "hdmi_rx", "R4", "value", "subsystems.HDMI_RX_DET_BOTTOM", "Device:R"},
            {"library", "hdmi_rx", "C1", "value", "subsystems.HDMI_RX_EDID_BYPASS", "Device:C"},
            {"library", "hdmi_tx", "C1", "value", "subsystems.HDMI_TX_RAIL_BYPASS", "Device:C"},
            {"library", "hdmi_tx", "C2", "value", "subsystems.HDMI_TX_RAIL_BYPASS", "Device:C"},
            {"library", "hdmi_tx", "C5", "value", "subsystems.HDMI_TX_RAIL_BULK", "Device:C"},
            {"library", "hdmi_tx", "C3", "value", "subsystems.HDMI_TX_CABLE_BYPASS", "Device:C"},
            {"library", "hdmi_tx", "C4", "value", "subsystems.HDMI_TX_CABLE_BULK", "Device:C"},
            {"library", "hdmi_tx", "R1", "value", "subsystems.HDMI_TX_STRAP_PULL", "Device:R"},
            {"library", "hdmi_tx", "R2", "value", "subsystems.HDMI_TX_STRAP_PULL", "Device:R"},
            {"library", "lcd", "L1", "value", "subsystems.LCD_BOOST_INDUCTOR", "SWPA4030S100MT:SWPA4030S100MT"},
            {"library", "lcd", "R1", "value", "subsystems.LCD_ISET_SENSE", "Device:R"},
            {"library", "lcd", "C1", "value", "subsystems.LCD_BOOST_CIN", "Device:C"},
            {"library", "lcd", "C2", "value", "subsystems.LCD_BOOST_COUT", "Device:C"},
            {"library", "lcd", "C3", "value", "subsystems.LCD_PANEL_BYPASS", "Device:C"},
            {"library", "lcd", "R2", "value", "subsystems.LCD_TOUCH_PULL", "Device:R"},
            {"library", "lcd", "R3", "value", "subsystems.LCD_TOUCH_PULL", "Device:R"},
            {"library", "lcd", "R5", "value", "subsystems.LCD_RESET_PULLDOWN", "Device:R"},
            {"library", "lcd", "R6", "value", "subsystems.LCD_DISP_PULLUP", "Device:R"},
            {"library", "lcd", "R7", "value", "subsystems.LCD_PCLK_DAMPING", "Device:R"},
            {"library", "lcd", "C4", "value", "subsystems.LCD_PANEL_BULK", "Device:C"},
            {"library", "lcd", "C5", "value", "subsystems.LCD_BOOST_HF", "Device:C"},
            {"library", "lcd", "R4", "value", "subsystems.LCD_BLPWM_PULLDOWN", "Device:R"},
            {"library", "microsd", "R1", "value", "subsystems.MICROSD_CARD_PULL", "Device:R"},
            {"library", "microsd", "R2", "value", "subsystems.MICROSD_CARD_PULL", "Device:R"},
            {"library", "microsd", "R3", "value", "subsystems.MICROSD_CARD_PULL", "Device:R"},
            {"library", "microsd", "R4", "value", "subsystems.MICROSD_CARD_PULL", "Device:R"},
            {"library", "microsd", "R5", "value", "subsystems.MICROSD_CARD_PULL", "Device:R"},
            {"library", "microsd", "R6", "value", "subsystems.MICROSD_DETECT_PULL", "Device:R"},
            {"library", "microsd", "C1", "value", "subsystems.MICROSD_HOST_BYPASS", "Device:C"},
            {"library", "microsd", "C2", "value", "subsystems.MICROSD_CARD_BYPASS", "Device:C"},
            {"library", "microsd", "C3", "value", "subsystems.MICROSD_CARD_BULK", "Device:C"},
            {"library", "microsd", "C4", "value", "subsystems.MICROSD_ESD_BYPASS", "Device:C"},
            {"library", "pd_input", "C1", "value", "subsystems.PD_INPUT_INLET_BYPASS", "Device:C"},
            {"library", "pd_input", "R3", "value", "subsystems.PD_INPUT_OVP_TOP", "Device:R"},
            {"library", "pd_input", "R4", "value", "subsystems.PD_INPUT_OVP_BOTTOM", "Device:R"},
            {"library", "pd_input", "R5", "value", "subsystems.PD_INPUT_ILIM_SET", "Device:R"},
            {"library", "pd_input", "C3", "value", "subsystems.PD_INPUT_DVDT_CAP", "Device:C"},
            {"library", "pd_input", "R6", "value", "subsystems.PD_INPUT_FAULT_PULL", "Device:R"},
            {"library", "pd_input", "C2", "value", "subsystems.PD_INPUT_FUSED_BULK", "Device:C"},
            {"library", "pmod", "R1", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"library", "pmod", "R2", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"library", "pmod", "R3", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"library", "pmod", "R4", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"library", "pmod", "R5", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"library", "pmod", "R6", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"library", "pmod", "R7", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"library", "pmod", "R8", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"library", "pmod", "R9", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"library", "pmod", "R10", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"library", "pmod", "R11", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"library", "pmod", "R12", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"library", "pmod", "R13", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"library", "pmod", "R14", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"library", "pmod", "R15", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"library", "pmod", "R16", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"library", "pmod", "C1", "value", "subsystems.PMOD_RAIL_BYPASS", "Device:C"},
            {"library", "pmod", "C2", "value", "subsystems.PMOD_RAIL_BULK", "Device:C"},
            {"library", "pmod", "C3", "value", "subsystems.PMOD_RAIL_BYPASS", "Device:C"},
            {"library", "pmod", "C4", "value", "subsystems.PMOD_RAIL_BULK", "Device:C"},
            {"library", "pmod_expansion", "R1", "value", "subsystems.PMOD_EXP_ILIM_SET", "Device:R"},
            {"library", "pmod_expansion", "C1", "value", "subsystems.PMOD_EXP_INPUT_BYPASS", "Device:C"},
            {"library", "pmod_expansion", "C2", "value", "subsystems.PMOD_EXP_INPUT_BULK", "Device:C"},
            {"library", "pmod_expansion", "C3", "value", "subsystems.PMOD_EXP_OUTPUT_BYPASS", "Device:C"},
            {"library", "pmod_expansion", "R2", "value", "subsystems.PMOD_EXP_ENABLE_PULLDOWN", "Device:R"},
            {"library", "pmod_expansion", "R3", "value", "subsystems.PMOD_EXP_LED_SERIES", "Device:R"},
            {"library", "pmod_expansion", "C4", "value", "subsystems.PMOD_EXP_SOCKET_BYPASS", "Device:C"},
            {"library", "pmod_expansion", "C5", "value", "subsystems.PMOD_EXP_SOCKET_BULK", "Device:C"},
            {"library", "power", "C1", "value", "subsystems.POWER_VIN_HF", "Device:C"},
            {"library", "power", "C25", "value", "subsystems.POWER_VIN_HF", "Device:C"},
            {"library", "power", "C2", "value", "subsystems.POWER_VIN_BULK", "Device:C"},
            {"library", "power", "C3", "value", "subsystems.POWER_VIN_BULK", "Device:C"},
            {"library", "power", "C24", "value", "subsystems.POWER_VCC_BYPASS", "Device:C"},
            {"library", "power", "R11", "value", "subsystems.POWER_BIAS_SERIES", "Device:R"},
            {"library", "power", "C28", "value", "subsystems.POWER_BIAS_BYPASS", "Device:C"},
            {"library", "power", "R10", "value", "subsystems.POWER_RT_FREQ", "Device:R"},
            {"library", "power", "C4", "value", "subsystems.POWER_BOOT_CAP", "Device:C"},
            {"library", "power", "L1", "value", "subsystems.POWER_SW_INDUCTOR", "Device:L"},
            {"library", "power", "C5", "value", "subsystems.POWER_COUT_BULK", "Device:C"},
            {"library", "power", "C6", "value", "subsystems.POWER_COUT_BULK", "Device:C"},
            {"library", "power", "C26", "value", "subsystems.POWER_COUT_BULK", "Device:C"},
            {"library", "power", "R1", "value", "subsystems.POWER_FB5V_TOP", "Device:R"},
            {"library", "power", "R2", "value", "subsystems.POWER_FB_BOTTOM", "Device:R"},
            {"library", "power", "C27", "value", "subsystems.POWER_CFF_CAP", "Device:C"},
            {"library", "power", "R12", "value", "subsystems.POWER_RFF_SERIES", "Device:R"},
            {"library", "power", "R3", "value", "subsystems.POWER_LED5V_SERIES", "Device:R"},
            {"library", "power", "C7", "value", "subsystems.POWER_VIN_HF", "Device:C"},
            {"library", "power", "C29", "value", "subsystems.POWER_VIN_HF", "Device:C"},
            {"library", "power", "C8", "value", "subsystems.POWER_5V_BULK", "Device:C"},
            {"library", "power", "C30", "value", "subsystems.POWER_5V_BULK", "Device:C"},
            {"library", "power", "C31", "value", "subsystems.POWER_VCC_BYPASS", "Device:C"},
            {"library", "power", "R13", "value", "subsystems.POWER_BIAS_SERIES", "Device:R"},
            {"library", "power", "C32", "value", "subsystems.POWER_BIAS_BYPASS", "Device:C"},
            {"library", "power", "R14", "value", "subsystems.POWER_RT_FREQ", "Device:R"},
            {"library", "power", "C9", "value", "subsystems.POWER_BOOT_CAP", "Device:C"},
            {"library", "power", "L2", "value", "subsystems.POWER_SW_INDUCTOR", "Device:L"},
            {"library", "power", "C10", "value", "subsystems.POWER_COUT_BULK", "Device:C"},
            {"library", "power", "C11", "value", "subsystems.POWER_COUT_BULK", "Device:C"},
            {"library", "power", "R4", "value", "subsystems.POWER_FB3V3_TOP", "Device:R"},
            {"library", "power", "R5", "value", "subsystems.POWER_FB_BOTTOM", "Device:R"},
            {"library", "power", "C23", "value", "subsystems.POWER_CFF_CAP", "Device:C"},
            {"library", "power", "R15", "value", "subsystems.POWER_RFF_SERIES", "Device:R"},
            {"library", "power", "R6", "value", "subsystems.POWER_LED_SERIES", "Device:R"},
            {"library", "power", "C12", "value", "subsystems.POWER_LDO_CAP", "Device:C"},
            {"library", "power", "C13", "value", "subsystems.POWER_LDO_CAP", "Device:C"},
            {"library", "power", "R7", "value", "subsystems.POWER_GATE_STOP", "Device:R"},
            {"library", "power", "R8", "value", "subsystems.POWER_GATE_PULLDOWN", "Device:R"},
            {"library", "power", "R9", "value", "subsystems.POWER_LED_SERIES", "Device:R"},
            {"library", "rj45_connector", "R1", "value", "subsystems.RJ45_LED_SERIES", "Device:R"},
            {"library", "rj45_connector", "R2", "value", "subsystems.RJ45_LED_SERIES", "Device:R"},
            {"library", "uart_bridge", "C1", "value", "subsystems.UART_BRIDGE_SUPPLY_BYPASS", "Device:C"},
            {"library", "uart_bridge", "C2", "value", "subsystems.UART_BRIDGE_VREGIN_BULK", "Device:C"},
            {"library", "uart_bridge", "C3", "value", "subsystems.UART_BRIDGE_SUPPLY_BYPASS", "Device:C"},
            {"library", "uart_bridge", "C4", "value", "subsystems.UART_BRIDGE_SUPPLY_BYPASS", "Device:C"},
            {"library", "uart_bridge", "R1", "value", "subsystems.UART_BRIDGE_RESET_PULL", "Device:R"},
            {"library", "uart_bridge", "R2", "value", "subsystems.UART_BRIDGE_SENSE_TOP", "Device:R"},
            {"library", "uart_bridge", "R3", "value", "subsystems.UART_BRIDGE_SENSE_BOTTOM", "Device:R"},
            {"library", "usb_jtag", "C1", "value", "subsystems.JTAG_LDO_CIN", "Device:C"},
            {"library", "usb_jtag", "C2", "value", "subsystems.JTAG_LDO_COUT", "Device:C"},
            {"library", "usb_jtag", "C3", "value", "subsystems.JTAG_SUPPLY_BYPASS", "Device:C"},
            {"library", "usb_jtag", "C4", "value", "subsystems.JTAG_SUPPLY_BYPASS", "Device:C"},
            {"library", "usb_jtag", "Y1", "value", "subsystems.JTAG_CRYSTAL_FREQ", "1C208000BC0R:1C208000BC0R"},
            {"library", "usb_jtag", "C5", "value", "subsystems.JTAG_CRYSTAL_LOAD", "Device:C"},
            {"library", "usb_jtag", "C6", "value", "subsystems.JTAG_CRYSTAL_LOAD", "Device:C"},
            {"library", "usb_jtag", "R1", "value", "subsystems.JTAG_RESET_PULL", "Device:R"},
            {"library", "usb_jtag", "R2", "value", "subsystems.JTAG_MODE_PULLDOWN", "Device:R"},
            {"library", "usb_jtag", "R3", "value", "subsystems.JTAG_MODE_PULLDOWN", "Device:R"},
            {"library", "usb_jtag", "C7", "value", "subsystems.JTAG_SUPPLY_BYPASS", "Device:C"},
            {"library", "usb_jtag", "R4", "value", "subsystems.JTAG_OE_PULLUP", "Device:R"},
            {"library", "usb_jtag_connector", "C1", "value", "subsystems.JTAG_CONN_VBUS_BULK", "Device:C"},
            {"library", "usb_jtag_connector", "R1", "value", "subsystems.JTAG_CONN_CC_RD", "Device:R"},
            {"library", "usb_jtag_connector", "R2", "value", "subsystems.JTAG_CONN_CC_RD", "Device:R"},
            {"library", "usb_pd", "C1", "value", "subsystems.USB_PD_VDD_BYPASS", "Device:C"},
            {"library", "usb_pd", "C2", "value", "subsystems.USB_PD_VDD_BULK", "Device:C"},
            {"library", "usb_pd", "C3", "value", "subsystems.USB_PD_VBUS_BYPASS", "Device:C"},
            {"library", "usb_pd", "C4", "value", "subsystems.USB_PD_CC_FILTER", "Device:C"},
            {"library", "usb_pd", "C5", "value", "subsystems.USB_PD_CC_FILTER", "Device:C"},
            {"library", "usb_uart_connector", "C1", "value", "subsystems.UART_CONN_VBUS_BULK", "Device:C"},
            {"library", "usb_uart_connector", "R1", "value", "subsystems.UART_CONN_CC_RD", "Device:R"},
            {"library", "usb_uart_connector", "R2", "value", "subsystems.UART_CONN_CC_RD", "Device:R"},
            {"library", "usbc_otg", "R5", "value", "subsystems.OTG_ENABLE_PULLDOWN", "Device:R"},
            {"library", "usbc_otg", "R3", "value", "subsystems.OTG_FAULT_PULLUP", "Device:R"},
            {"library", "usbc_otg", "C1", "value", "subsystems.OTG_INPUT_BYPASS", "Device:C"},
            {"library", "usbc_otg", "C2", "value", "subsystems.OTG_VBUS_MLCC", "Device:C"},
            {"library", "usbc_otg", "C3", "value", "subsystems.OTG_VBUS_BULK", "RVT1C101M0605_100UF_16V:RVT1C101M0605_100UF_16V"},
            {"library", "usbc_otg", "R1", "value", "subsystems.OTG_CC_RP", "Device:R"},
            {"library", "usbc_otg", "R2", "value", "subsystems.OTG_CC_RP", "Device:R"},
            {"library", "usbc_otg", "R4", "value", "subsystems.OTG_ID_STRAP", "Device:R"},
            {"carrier", "board_aux", "R1", "value", "carrier.board_aux.iset", "Device:R"},
            {"carrier", "board_aux", "C1", "value", "carrier.board_aux.decap", "Device:C"},
            {"carrier", "board_aux", "C2", "value", "carrier.board_aux.decap", "Device:C"},
            {"carrier", "board_aux", "C3", "value", "carrier.board_aux.out_bulk", "Device:C"},
            {"carrier", "board_aux", "R2", "value", "carrier.board_aux.en_pulldown", "Device:R"},
            {"carrier", "board_aux", "R3", "value", "carrier.board_aux.led_ballast", "Device:R"},
            {"carrier", "board_aux", "C4", "value", "carrier.board_aux.decap", "Device:C"},
            {"carrier", "board_aux", "R4", "value", "carrier.board_aux.iso_en_pullup", "Device:R"},
            {"carrier", "board_aux", "R5", "value", "carrier.board_aux.bus_pullup", "Device:R"},
            {"carrier", "board_aux", "R6", "value", "carrier.board_aux.bus_pullup", "Device:R"},
            {"carrier", "board_aux", "C5", "value", "carrier.board_aux.decap", "Device:C"},
            {"carrier", "board_services", "C1", "value", "carrier.board_services.decap", "Device:C"},
            {"carrier", "board_services", "R1", "value", "carrier.board_services.int_pullup", "Device:R"},
            {"carrier", "board_services", "C2", "value", "carrier.board_services.decap", "Device:C"},
            {"carrier", "board_services", "C3", "value", "carrier.board_services.decap", "Device:C"},
            {"carrier", "board_services", "R2", "value", "carrier.board_services.wdi_series_r", "Device:R"},
            {"carrier", "bringup_en", "R1", "value", "carrier.bringup_en.dip_pulldown", "Device:R"},
            {"carrier", "bringup_en", "R2", "value", "carrier.bringup_en.override_pullup", "Device:R"},
            {"carrier", "bringup_en", "C1", "value", "carrier.bringup_en.gate_decap", "Device:C"},
            {"carrier", "bringup_en", "R3", "value", "carrier.bringup_en.dip_pulldown", "Device:R"},
            {"carrier", "bringup_en", "R4", "value", "carrier.bringup_en.override_pullup", "Device:R"},
            {"carrier", "bringup_en", "C2", "value", "carrier.bringup_en.gate_decap", "Device:C"},
            {"carrier", "bringup_en", "R5", "value", "carrier.bringup_en.dip_pulldown", "Device:R"},
            {"carrier", "bringup_en", "R6", "value", "carrier.bringup_en.override_pullup", "Device:R"},
            {"carrier", "bringup_en", "C3", "value", "carrier.bringup_en.gate_decap", "Device:C"},
            {"carrier", "bringup_en_modules", "R1", "value", "carrier.bringup_en_modules.dip_pulldown", "Device:R"},
            {"carrier", "bringup_en_modules", "R2", "value", "carrier.bringup_en_modules.override_pullup", "Device:R"},
            {"carrier", "bringup_en_modules", "C1", "value", "carrier.bringup_en_modules.gate_decap", "Device:C"},
            {"carrier", "bringup_en_modules", "R3", "value", "carrier.bringup_en_modules.dip_pulldown", "Device:R"},
            {"carrier", "bringup_en_modules", "R4", "value", "carrier.bringup_en_modules.override_pullup", "Device:R"},
            {"carrier", "bringup_en_modules", "C2", "value", "carrier.bringup_en_modules.gate_decap", "Device:C"},
            {"carrier", "bringup_en_modules", "R5", "value", "carrier.bringup_en_modules.dip_pulldown", "Device:R"},
            {"carrier", "bringup_en_modules", "R6", "value", "carrier.bringup_en_modules.override_pullup", "Device:R"},
            {"carrier", "bringup_en_modules", "C3", "value", "carrier.bringup_en_modules.gate_decap", "Device:C"},
            {"carrier", "bringup_en_modules", "R7", "value", "carrier.bringup_en_modules.dip_pulldown", "Device:R"},
            {"carrier", "bringup_en_modules", "R8", "value", "carrier.bringup_en_modules.override_pullup", "Device:R"},
            {"carrier", "bringup_en_modules", "C4", "value", "carrier.bringup_en_modules.gate_decap", "Device:C"},
            {"carrier", "bringup_en_modules", "R9", "value", "carrier.bringup_en_modules.dip_pulldown", "Device:R"},
            {"carrier", "bringup_en_modules", "R10", "value", "carrier.bringup_en_modules.override_pullup", "Device:R"},
            {"carrier", "bringup_en_modules", "C5", "value", "carrier.bringup_en_modules.gate_decap", "Device:C"},
            {"carrier", "bringup_en_modules", "R11", "value", "carrier.bringup_en_modules.dip_pulldown", "Device:R"},
            {"carrier", "bringup_en_modules", "R12", "value", "carrier.bringup_en_modules.override_pullup", "Device:R"},
            {"carrier", "bringup_en_modules", "C6", "value", "carrier.bringup_en_modules.gate_decap", "Device:C"},
            {"carrier", "bringup_en_modules", "R13", "value", "carrier.bringup_en_modules.dip_pulldown", "Device:R"},
            {"carrier", "bringup_en_modules", "R14", "value", "carrier.bringup_en_modules.override_pullup", "Device:R"},
            {"carrier", "bringup_en_modules", "C7", "value", "carrier.bringup_en_modules.gate_decap", "Device:C"},
            {"carrier", "bringup_en_modules", "R15", "value", "carrier.bringup_en_modules.dip_pulldown", "Device:R"},
            {"carrier", "bringup_en_modules", "R16", "value", "carrier.bringup_en_modules.override_pullup", "Device:R"},
            {"carrier", "bringup_en_modules", "C8", "value", "carrier.bringup_en_modules.gate_decap", "Device:C"},
            {"carrier", "bringup_en_modules", "R17", "value", "carrier.bringup_en_modules.dip_pulldown", "Device:R"},
            {"carrier", "bringup_en_modules", "C9", "value", "carrier.bringup_en_modules.gate_decap", "Device:C"},
            {"carrier", "bringup_en_modules", "R18", "value", "carrier.bringup_en_modules.dip_pulldown", "Device:R"},
            {"carrier", "bringup_en_modules", "R19", "value", "carrier.bringup_en_modules.override_pullup", "Device:R"},
            {"carrier", "bringup_en_modules", "C10", "value", "carrier.bringup_en_modules.gate_decap", "Device:C"},
            {"carrier", "bringup_en_modules", "R20", "value", "carrier.bringup_en_modules.dip_pulldown", "Device:R"},
            {"carrier", "bringup_en_modules", "R21", "value", "carrier.bringup_en_modules.override_pullup", "Device:R"},
            {"carrier", "bringup_en_modules", "C11", "value", "carrier.bringup_en_modules.gate_decap", "Device:C"},
            {"carrier", "bringup_modules", "R1", "value", "carrier.bringup_modules.iset_523ma", "Device:R"},
            {"carrier", "bringup_modules", "C1", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "C2", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "R2", "value", "carrier.bringup_modules.led_r_3v3", "Device:R"},
            {"carrier", "bringup_modules", "R3", "value", "carrier.bringup_modules.iset_523ma", "Device:R"},
            {"carrier", "bringup_modules", "C3", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "C4", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "R4", "value", "carrier.bringup_modules.led_r_3v3", "Device:R"},
            {"carrier", "bringup_modules", "R5", "value", "carrier.bringup_modules.iset_1a", "Device:R"},
            {"carrier", "bringup_modules", "C5", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "C6", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "R6", "value", "carrier.bringup_modules.led_r_3v3", "Device:R"},
            {"carrier", "bringup_modules", "R7", "value", "carrier.bringup_modules.iset_523ma", "Device:R"},
            {"carrier", "bringup_modules", "C7", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "C8", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "R8", "value", "carrier.bringup_modules.led_r_3v3", "Device:R"},
            {"carrier", "bringup_modules", "R9", "value", "carrier.bringup_modules.iset_1a", "Device:R"},
            {"carrier", "bringup_modules", "C9", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "C10", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "R10", "value", "carrier.bringup_modules.led_r_3v3", "Device:R"},
            {"carrier", "bringup_modules", "R11", "value", "carrier.bringup_modules.iset_1a", "Device:R"},
            {"carrier", "bringup_modules", "C11", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "C12", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "R12", "value", "carrier.bringup_modules.led_r_5v", "Device:R"},
            {"carrier", "bringup_modules", "R13", "value", "carrier.bringup_modules.iset_523ma", "Device:R"},
            {"carrier", "bringup_modules", "C13", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "C14", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "R14", "value", "carrier.bringup_modules.led_r_3v3", "Device:R"},
            {"carrier", "bringup_modules", "R15", "value", "carrier.bringup_modules.iset_523ma", "Device:R"},
            {"carrier", "bringup_modules", "C15", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "C16", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "R16", "value", "carrier.bringup_modules.led_r_3v3", "Device:R"},
            {"carrier", "bringup_modules", "R17", "value", "carrier.bringup_modules.iset_523ma", "Device:R"},
            {"carrier", "bringup_modules", "C17", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "C18", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "R18", "value", "carrier.bringup_modules.led_r_5v", "Device:R"},
            {"carrier", "bringup_modules", "R19", "value", "carrier.bringup_modules.iset_1a", "Device:R"},
            {"carrier", "bringup_modules", "C19", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "C20", "value", "carrier.bringup_modules.switch_decap", "Device:C"},
            {"carrier", "bringup_modules", "R20", "value", "carrier.bringup_modules.led_r_5v", "Device:R"},
            {"carrier", "bringup_modules", "R21", "value", "carrier.bringup_modules.sd_bleed", "Device:R"},
            {"carrier", "bringup_rails", "C1", "value", "carrier.bringup_rails.expander_decap", "Device:C"},
            {"carrier", "bringup_rails", "R1", "value", "carrier.bringup_rails.spare_pulldown", "Device:R"},
            {"carrier", "bringup_rails", "R2", "value", "carrier.bringup_rails.spare_pulldown", "Device:R"},
            {"carrier", "bringup_rails", "R3", "value", "carrier.bringup_rails.spare_pulldown", "Device:R"},
            {"carrier", "bringup_rails", "R4", "value", "carrier.bringup_rails.bus_pullup", "Device:R"},
            {"carrier", "bringup_rails", "R5", "value", "carrier.bringup_rails.bus_pullup", "Device:R"},
            {"carrier", "bringup_rails", "R6", "value", "carrier.bringup_rails.int_pullup", "Device:R"},
            {"carrier", "bringup_rails", "C2", "value", "carrier.bringup_rails.debounce_cap", "Device:C"},
            {"carrier", "bringup_rails", "R7", "value", "carrier.bringup_rails.button_pullup", "Device:R"},
            {"carrier", "bringup_rails", "C3", "value", "carrier.bringup_rails.debounce_cap", "Device:C"},
            {"carrier", "bringup_rails", "R8", "value", "carrier.bringup_rails.button_pullup", "Device:R"},
            {"carrier", "bringup_rails", "C4", "value", "carrier.bringup_rails.debounce_cap", "Device:C"},
            {"carrier", "bringup_rails", "R9", "value", "carrier.bringup_rails.pudc_strap", "Device:R"},
            {"carrier", "debug_boot", "R1", "value", "carrier.debug_boot.jtag_pullup", "Device:R"},
            {"carrier", "debug_boot", "R2", "value", "carrier.debug_boot.jtag_pullup", "Device:R"},
            {"carrier", "debug_boot", "R3", "value", "carrier.debug_boot.boot0_series_r", "Device:R"},
            {"carrier", "debug_boot", "R4", "value", "carrier.debug_boot.bootsel_pullup", "Device:R"},
            {"carrier", "debug_boot", "R5", "value", "carrier.debug_boot.bootsel_pullup", "Device:R"},
            {"carrier", "debug_boot", "R6", "value", "carrier.debug_boot.bootsel_pullup", "Device:R"},
            {"carrier", "fmc", "C1", "value", "carrier.fmc.rail_bulk", "Device:C"},
            {"carrier", "fmc", "C2", "value", "carrier.fmc.rail_hf", "Device:C"},
            {"carrier", "fmc", "C3", "value", "carrier.fmc.ldo_in", "Device:C"},
            {"carrier", "fmc", "C4", "value", "carrier.fmc.ldo_out", "Device:C"},
            {"carrier", "fmc", "C5", "value", "carrier.fmc.header_vadj_hf", "Device:C"},
            {"carrier", "hdmi_rx_term", "R1", "value", "carrier.hdmi_rx_term.term", "Device:R"},
            {"carrier", "hdmi_rx_term", "R2", "value", "carrier.hdmi_rx_term.term", "Device:R"},
            {"carrier", "hdmi_rx_term", "R3", "value", "carrier.hdmi_rx_term.term", "Device:R"},
            {"carrier", "hdmi_rx_term", "R4", "value", "carrier.hdmi_rx_term.term", "Device:R"},
            {"carrier", "hdmi_rx_term", "R5", "value", "carrier.hdmi_rx_term.term", "Device:R"},
            {"carrier", "hdmi_rx_term", "R6", "value", "carrier.hdmi_rx_term.term", "Device:R"},
            {"carrier", "hdmi_rx_term", "R7", "value", "carrier.hdmi_rx_term.term", "Device:R"},
            {"carrier", "hdmi_rx_term", "R8", "value", "carrier.hdmi_rx_term.term", "Device:R"},
            {"carrier", "hdmi_rx_term", "C1", "value", "carrier.hdmi_rx_term.avcc_hf", "Device:C"},
            {"carrier", "hdmi_rx_term", "C2", "value", "carrier.hdmi_rx_term.avcc_reservoir", "Device:C"},
            {"carrier", "motor_pwm", "C1", "value", "carrier.motor_pwm.switch_decap", "Device:C"},
            {"carrier", "motor_pwm", "R1", "value", "carrier.motor_pwm.oe_pullup", "Device:R"},
            {"carrier", "motor_pwm", "R2", "value", "carrier.motor_pwm.servo_iset", "Device:R"},
            {"carrier", "motor_pwm", "C2", "value", "carrier.motor_pwm.switch_decap", "Device:C"},
            {"carrier", "motor_pwm", "C3", "value", "carrier.motor_pwm.servo_holdup", "Device:C"},
            {"carrier", "motor_sense", "C1", "value", "carrier.motor_sense.rail_hf", "Device:C"},
            {"carrier", "motor_sense", "RS1", "value", "carrier.motor_sense.shunt", "RLM12FTCMR010:RLM12FTCMR010"},
            {"carrier", "motor_sense", "C2", "value", "carrier.motor_sense.supply_hf", "Device:C"},
            {"carrier", "motor_sense", "C3", "value", "carrier.motor_sense.supply_bulk", "Device:C"},
            {"carrier", "motor_sense", "R1", "value", "carrier.motor_sense.fault_pullup", "Device:R"},
            {"carrier", "motor_sense", "C4", "value", "carrier.motor_sense.rail_bulk", "Device:C_Polarized"},
            {"carrier", "power_mon", "RS1", "value", "carrier.power_mon.shunt_3a", "RLM12FTCMR010:RLM12FTCMR010"},
            {"carrier", "power_mon", "RS2", "value", "carrier.power_mon.shunt_3a", "RLM12FTCMR010:RLM12FTCMR010"},
            {"carrier", "power_mon", "RS3", "value", "carrier.power_mon.shunt_3a", "RLM12FTCMR010:RLM12FTCMR010"},
            {"carrier", "power_mon", "RS4", "value", "carrier.power_mon.shunt_600ma", "RLM12FTCMR020:RLM12FTCMR020"},
            {"carrier", "power_mon", "C1", "value", "carrier.power_mon.supply_hf", "Device:C"},
            {"carrier", "power_mon", "C2", "value", "carrier.power_mon.supply_hf", "Device:C"},
            {"carrier", "power_mon", "C3", "value", "carrier.power_mon.supply_bulk", "Device:C"},
            {"carrier", "power_mon", "R1", "value", "carrier.power_mon.alert_pullup", "Device:R"},
            {"carrier", "power_som", "R12", "value", "carrier.power_som.en_series_r", "Device:R"},
            {"carrier", "power_som", "C20", "value", "carrier.power_som.en_bypass", "Device:C"},
            {"carrier", "power_som", "C14", "value", "carrier.power_som.input_hf", "Device:C"},
            {"carrier", "power_som", "C25", "value", "carrier.power_som.input_hf", "Device:C"},
            {"carrier", "power_som", "C15", "value", "carrier.power_som.input_bulk", "Device:C"},
            {"carrier", "power_som", "C16", "value", "carrier.power_som.input_bulk", "Device:C"},
            {"carrier", "power_som", "C22", "value", "carrier.power_som.vcc_bypass", "Device:C"},
            {"carrier", "power_som", "R17", "value", "carrier.power_som.bias_series_r", "Device:R"},
            {"carrier", "power_som", "C23", "value", "carrier.power_som.bias_bypass", "Device:C"},
            {"carrier", "power_som", "R18", "value", "carrier.power_som.rt", "Device:R"},
            {"carrier", "power_som", "C17", "value", "carrier.power_som.boot_cap", "Device:C"},
            {"carrier", "power_som", "L3", "value", "carrier.power_som.inductor", "Device:L"},
            {"carrier", "power_som", "C18", "value", "carrier.power_som.output_bulk", "Device:C"},
            {"carrier", "power_som", "C19", "value", "carrier.power_som.output_bulk", "Device:C"},
            {"carrier", "power_som", "R14", "value", "carrier.power_som.fb_top", "Device:R"},
            {"carrier", "power_som", "R15", "value", "carrier.power_som.fb_bottom", "Device:R"},
            {"carrier", "power_som", "C21", "value", "carrier.power_som.ff_cap", "Device:C"},
            {"carrier", "power_som", "R19", "value", "carrier.power_som.ff_series_r", "Device:R"},
            {"carrier", "power_som", "R16", "value", "carrier.power_som.pg_led_r", "Device:R"},
            {"carrier", "som_decoupling", "C1", "value", "carrier.som_decoupling.bulk", "Device:C"},
            {"carrier", "som_decoupling", "C2", "value", "carrier.som_decoupling.bulk", "Device:C"},
            {"carrier", "som_decoupling", "C3", "value", "carrier.som_decoupling.hf", "Device:C"},
            {"carrier", "som_decoupling", "C4", "value", "carrier.som_decoupling.hf", "Device:C"},
            {"carrier", "som_decoupling", "C5", "value", "carrier.som_decoupling.hf", "Device:C"},
            {"carrier", "som_decoupling", "C6", "value", "carrier.som_decoupling.hf", "Device:C"},
            {"carrier", "som_decoupling", "C7", "value", "carrier.som_decoupling.bulk", "Device:C"},
            {"carrier", "som_decoupling", "C8", "value", "carrier.som_decoupling.bulk", "Device:C"},
            {"carrier", "som_decoupling", "C9", "value", "carrier.som_decoupling.hf", "Device:C"},
            {"carrier", "som_decoupling", "C10", "value", "carrier.som_decoupling.hf", "Device:C"},
            {"carrier", "som_decoupling", "C11", "value", "carrier.som_decoupling.hf", "Device:C"},
            {"carrier", "som_decoupling", "C12", "value", "carrier.som_decoupling.hf", "Device:C"},
            {"carrier", "som_decoupling", "C13", "value", "carrier.som_decoupling.bulk", "Device:C"},
            {"carrier", "som_decoupling", "C14", "value", "carrier.som_decoupling.bulk", "Device:C"},
            {"carrier", "som_decoupling", "C15", "value", "carrier.som_decoupling.hf", "Device:C"},
            {"carrier", "som_decoupling", "C16", "value", "carrier.som_decoupling.hf", "Device:C"},
            {"carrier", "som_decoupling", "C17", "value", "carrier.som_decoupling.hf", "Device:C"},
            {"carrier", "som_decoupling", "C18", "value", "carrier.som_decoupling.hf", "Device:C"},
            {"carrier", "user_io", "R1", "value", "carrier.user_io.led_r_red", "Device:R"},
            {"carrier", "user_io", "R2", "value", "carrier.user_io.led_r_high_vf", "Device:R"},
            {"carrier", "user_io", "R3", "value", "carrier.user_io.led_r_high_vf", "Device:R"},
            {"carrier", "user_io", "R4", "value", "carrier.user_io.led_r_high_vf", "Device:R"},
            {"carrier", "user_io", "C1", "value", "carrier.user_io.led_rail_hf", "Device:C"},
            {"carrier", "user_io", "R5", "value", "carrier.user_io.button_pullup", "Device:R"},
            {"carrier", "user_io", "R6", "value", "carrier.user_io.button_pullup", "Device:R"},
            {"carrier", "user_io", "R7", "value", "carrier.user_io.button_pullup", "Device:R"},
            {"carrier", "user_io", "R8", "value", "carrier.user_io.button_pullup", "Device:R"},
            {"devkit_mini", "debug_boot", "R1", "value", "devkit_mini.debug_boot.jtag_pullup", "Device:R"},
            {"devkit_mini", "debug_boot", "R2", "value", "devkit_mini.debug_boot.jtag_pullup", "Device:R"},
            {"devkit_mini", "debug_boot", "R3", "value", "devkit_mini.debug_boot.boot0_series_r", "Device:R"},
            {"devkit_mini", "debug_boot", "R4", "value", "devkit_mini.debug_boot.bootsel_pullup", "Device:R"},
            {"devkit_mini", "debug_boot", "R5", "value", "devkit_mini.debug_boot.bootsel_pullup", "Device:R"},
            {"devkit_mini", "debug_boot", "R6", "value", "devkit_mini.debug_boot.bootsel_pullup", "Device:R"},
            {"devkit_mini", "debug_boot", "R7", "value", "devkit_mini.debug_boot.i2c_pullup", "Device:R"},
            {"devkit_mini", "debug_boot", "R8", "value", "devkit_mini.debug_boot.i2c_pullup", "Device:R"},
            {"devkit_mini", "power_mon", "RS1", "value", "devkit_mini.power_mon.shunt_3a", "RLM12FTCMR010:RLM12FTCMR010"},
            {"devkit_mini", "power_mon", "RS2", "value", "devkit_mini.power_mon.shunt_3a", "RLM12FTCMR010:RLM12FTCMR010"},
            {"devkit_mini", "power_mon", "RS3", "value", "devkit_mini.power_mon.shunt_3a", "RLM12FTCMR010:RLM12FTCMR010"},
            {"devkit_mini", "power_mon", "RS4", "value", "devkit_mini.power_mon.shunt_600ma", "RLM12FTCMR020:RLM12FTCMR020"},
            {"devkit_mini", "power_mon", "C1", "value", "devkit_mini.power_mon.supply_hf", "Device:C"},
            {"devkit_mini", "power_mon", "C2", "value", "devkit_mini.power_mon.supply_hf", "Device:C"},
            {"devkit_mini", "power_mon", "C3", "value", "devkit_mini.power_mon.supply_bulk", "Device:C"},
            {"devkit_mini", "power_mon", "R1", "value", "devkit_mini.power_mon.alert_pullup", "Device:R"},
            {"devkit_mini", "power_som", "R12", "value", "devkit_mini.power_som.en_series_r", "Device:R"},
            {"devkit_mini", "power_som", "C20", "value", "devkit_mini.power_som.en_bypass", "Device:C"},
            {"devkit_mini", "power_som", "C14", "value", "devkit_mini.power_som.input_hf", "Device:C"},
            {"devkit_mini", "power_som", "C25", "value", "devkit_mini.power_som.input_hf", "Device:C"},
            {"devkit_mini", "power_som", "C15", "value", "devkit_mini.power_som.input_bulk", "Device:C"},
            {"devkit_mini", "power_som", "C16", "value", "devkit_mini.power_som.input_bulk", "Device:C"},
            {"devkit_mini", "power_som", "C22", "value", "devkit_mini.power_som.vcc_bypass", "Device:C"},
            {"devkit_mini", "power_som", "R17", "value", "devkit_mini.power_som.bias_series_r", "Device:R"},
            {"devkit_mini", "power_som", "C23", "value", "devkit_mini.power_som.bias_bypass", "Device:C"},
            {"devkit_mini", "power_som", "R18", "value", "devkit_mini.power_som.rt", "Device:R"},
            {"devkit_mini", "power_som", "C17", "value", "devkit_mini.power_som.boot_cap", "Device:C"},
            {"devkit_mini", "power_som", "L3", "value", "devkit_mini.power_som.inductor", "Device:L"},
            {"devkit_mini", "power_som", "C18", "value", "devkit_mini.power_som.output_bulk", "Device:C"},
            {"devkit_mini", "power_som", "C19", "value", "devkit_mini.power_som.output_bulk", "Device:C"},
            {"devkit_mini", "power_som", "R14", "value", "devkit_mini.power_som.fb_top", "Device:R"},
            {"devkit_mini", "power_som", "R15", "value", "devkit_mini.power_som.fb_bottom", "Device:R"},
            {"devkit_mini", "power_som", "C21", "value", "devkit_mini.power_som.ff_cap", "Device:C"},
            {"devkit_mini", "power_som", "R19", "value", "devkit_mini.power_som.ff_series_r", "Device:R"},
            {"devkit_mini", "power_som", "R16", "value", "devkit_mini.power_som.pg_led_r", "Device:R"},
            {"devkit_mini", "som_decoupling", "C1", "value", "devkit_mini.som_decoupling.bulk", "Device:C"},
            {"devkit_mini", "som_decoupling", "C2", "value", "devkit_mini.som_decoupling.bulk", "Device:C"},
            {"devkit_mini", "som_decoupling", "C3", "value", "devkit_mini.som_decoupling.hf", "Device:C"},
            {"devkit_mini", "som_decoupling", "C4", "value", "devkit_mini.som_decoupling.hf", "Device:C"},
            {"devkit_mini", "som_decoupling", "C5", "value", "devkit_mini.som_decoupling.hf", "Device:C"},
            {"devkit_mini", "som_decoupling", "C6", "value", "devkit_mini.som_decoupling.hf", "Device:C"},
            {"devkit_mini", "som_decoupling", "C7", "value", "devkit_mini.som_decoupling.bulk", "Device:C"},
            {"devkit_mini", "som_decoupling", "C8", "value", "devkit_mini.som_decoupling.bulk", "Device:C"},
            {"devkit_mini", "som_decoupling", "C9", "value", "devkit_mini.som_decoupling.hf", "Device:C"},
            {"devkit_mini", "som_decoupling", "C10", "value", "devkit_mini.som_decoupling.hf", "Device:C"},
            {"devkit_mini", "som_decoupling", "C11", "value", "devkit_mini.som_decoupling.hf", "Device:C"},
            {"devkit_mini", "som_decoupling", "C12", "value", "devkit_mini.som_decoupling.hf", "Device:C"},
            {"devkit_mini", "som_decoupling", "C13", "value", "devkit_mini.som_decoupling.bulk", "Device:C"},
            {"devkit_mini", "som_decoupling", "C14", "value", "devkit_mini.som_decoupling.bulk", "Device:C"},
            {"devkit_mini", "som_decoupling", "C15", "value", "devkit_mini.som_decoupling.hf", "Device:C"},
            {"devkit_mini", "som_decoupling", "C16", "value", "devkit_mini.som_decoupling.hf", "Device:C"},
            {"devkit_mini", "som_decoupling", "C17", "value", "devkit_mini.som_decoupling.hf", "Device:C"},
            {"devkit_mini", "som_decoupling", "C18", "value", "devkit_mini.som_decoupling.hf", "Device:C"},
            {"carrier", "board_aux", "STM32_I2C2_SCL", "speed_hz", "carrier.board_aux.i2c_speed", "i2c"},
            {"carrier", "board_aux", "STM32_I2C2_SDA", "speed_hz", "carrier.board_aux.i2c_speed", "i2c"},
            {"carrier", "board_aux", "AUX_I2C_SCL", "speed_hz", "carrier.board_aux.i2c_speed", "i2c"},
            {"carrier", "board_aux", "AUX_I2C_SDA", "speed_hz", "carrier.board_aux.i2c_speed", "i2c"},
            {"carrier", "board_qwiic", "AUX_I2C_SDA", "speed_hz", "carrier.board_qwiic.i2c_speed", "i2c"},
            {"carrier", "board_qwiic", "AUX_I2C_SCL", "speed_hz", "carrier.board_qwiic.i2c_speed", "i2c"},
            {"carrier", "board_services", "AUX_I2C_SCL", "speed_hz", "carrier.board_services.i2c_speed", "i2c"},
            {"carrier", "board_services", "AUX_I2C_SDA", "speed_hz", "carrier.board_services.i2c_speed", "i2c"},
            {"carrier", "bringup_rails", "STM32_I2C2_SCL", "speed_hz", "carrier.bringup_rails.i2c_speed", "i2c"},
            {"carrier", "bringup_rails", "STM32_I2C2_SDA", "speed_hz", "carrier.bringup_rails.i2c_speed", "i2c"},
            {"carrier", "fmc", "FMC_CLK0_M2C_P", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_CLK0_M2C_N", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_CLK1_M2C_P", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_CLK1_M2C_N", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA00_CC_P", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA00_CC_N", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA01_CC_P", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA01_CC_N", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA02_P", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA02_N", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA03_P", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA03_N", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA04_P", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA04_N", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA05_P", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA05_N", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA06_P", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA06_N", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA07_P", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA07_N", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA08_P", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA08_N", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA09_P", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA09_N", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA10_P", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA10_N", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA11_P", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "fmc", "FMC_LA11_N", "impedance", "carrier.fmc.pair_impedance", "diff_pair"},
            {"carrier", "motor_sense", "STM32_I2C2_SDA", "speed_hz", "carrier.motor_sense.i2c_speed", "i2c"},
            {"carrier", "motor_sense", "STM32_I2C2_SCL", "speed_hz", "carrier.motor_sense.i2c_speed", "i2c"},
            {"carrier", "power_mon", "STM32_I2C2_SDA", "speed_hz", "carrier.power_mon.i2c_speed", "i2c"},
            {"carrier", "power_mon", "STM32_I2C2_SCL", "speed_hz", "carrier.power_mon.i2c_speed", "i2c"},
            {"devkit_mini", "debug_boot", "STM32_I2C2_SCL", "speed_hz", "devkit_mini.debug_boot.i2c_speed", "i2c"},
            {"devkit_mini", "debug_boot", "STM32_I2C2_SDA", "speed_hz", "devkit_mini.debug_boot.i2c_speed", "i2c"},
            {"devkit_mini", "power_mon", "STM32_I2C2_SDA", "speed_hz", "devkit_mini.power_mon.i2c_speed", "i2c"},
            {"devkit_mini", "power_mon", "STM32_I2C2_SCL", "speed_hz", "devkit_mini.power_mon.i2c_speed", "i2c"},
            {"carrier", "camera", "R1", "value", "subsystems.CAMERA_LANE_TERM", "Device:R"},
            {"carrier", "camera", "R2", "value", "subsystems.CAMERA_LANE_TERM", "Device:R"},
            {"carrier", "camera", "R3", "value", "subsystems.CAMERA_LANE_TERM", "Device:R"},
            {"carrier", "camera", "R4", "value", "subsystems.CAMERA_I2C_PULL", "Device:R"},
            {"carrier", "camera", "R5", "value", "subsystems.CAMERA_I2C_PULL", "Device:R"},
            {"carrier", "camera", "C1", "value", "subsystems.CAMERA_RAIL_BYPASS", "Device:C"},
            {"carrier", "camera", "C2", "value", "subsystems.CAMERA_RAIL_BULK", "Device:C"},
            {"carrier", "ethernet", "R1", "value", "subsystems.ETHERNET_BOB_SMITH_R", "Device:R"},
            {"carrier", "ethernet", "C1", "value", "subsystems.ETHERNET_BOB_SMITH_C", "Device:C"},
            {"carrier", "ethernet", "R2", "value", "subsystems.ETHERNET_BOB_SMITH_R", "Device:R"},
            {"carrier", "ethernet", "C2", "value", "subsystems.ETHERNET_BOB_SMITH_C", "Device:C"},
            {"carrier", "ethernet", "R3", "value", "subsystems.ETHERNET_BOB_SMITH_R", "Device:R"},
            {"carrier", "ethernet", "C3", "value", "subsystems.ETHERNET_BOB_SMITH_C", "Device:C"},
            {"carrier", "ethernet", "R4", "value", "subsystems.ETHERNET_BOB_SMITH_R", "Device:R"},
            {"carrier", "ethernet", "C4", "value", "subsystems.ETHERNET_BOB_SMITH_C", "Device:C"},
            {"carrier", "ethernet", "C5", "value", "subsystems.ETHERNET_BOB_SMITH_C", "Device:C"},
            {"carrier", "hdmi_rx", "R1", "value", "subsystems.HDMI_RX_HPD_ASSERT", "Device:R"},
            {"carrier", "hdmi_rx", "R2", "value", "subsystems.HDMI_RX_CEC_PULL", "Device:R"},
            {"carrier", "hdmi_rx", "R3", "value", "subsystems.HDMI_RX_DET_TOP", "Device:R"},
            {"carrier", "hdmi_rx", "R4", "value", "subsystems.HDMI_RX_DET_BOTTOM", "Device:R"},
            {"carrier", "hdmi_rx", "C1", "value", "subsystems.HDMI_RX_EDID_BYPASS", "Device:C"},
            {"carrier", "hdmi_tx", "C1", "value", "subsystems.HDMI_TX_RAIL_BYPASS", "Device:C"},
            {"carrier", "hdmi_tx", "C2", "value", "subsystems.HDMI_TX_RAIL_BYPASS", "Device:C"},
            {"carrier", "hdmi_tx", "C5", "value", "subsystems.HDMI_TX_RAIL_BULK", "Device:C"},
            {"carrier", "hdmi_tx", "C3", "value", "subsystems.HDMI_TX_CABLE_BYPASS", "Device:C"},
            {"carrier", "hdmi_tx", "C4", "value", "subsystems.HDMI_TX_CABLE_BULK", "Device:C"},
            {"carrier", "hdmi_tx", "R1", "value", "subsystems.HDMI_TX_STRAP_PULL", "Device:R"},
            {"carrier", "hdmi_tx", "R2", "value", "subsystems.HDMI_TX_STRAP_PULL", "Device:R"},
            {"carrier", "lcd", "L1", "value", "subsystems.LCD_BOOST_INDUCTOR", "SWPA4030S100MT:SWPA4030S100MT"},
            {"carrier", "lcd", "R1", "value", "subsystems.LCD_ISET_SENSE", "Device:R"},
            {"carrier", "lcd", "C1", "value", "subsystems.LCD_BOOST_CIN", "Device:C"},
            {"carrier", "lcd", "C2", "value", "subsystems.LCD_BOOST_COUT", "Device:C"},
            {"carrier", "lcd", "C3", "value", "subsystems.LCD_PANEL_BYPASS", "Device:C"},
            {"carrier", "lcd", "R2", "value", "subsystems.LCD_TOUCH_PULL", "Device:R"},
            {"carrier", "lcd", "R3", "value", "subsystems.LCD_TOUCH_PULL", "Device:R"},
            {"carrier", "lcd", "R5", "value", "subsystems.LCD_RESET_PULLDOWN", "Device:R"},
            {"carrier", "lcd", "R6", "value", "subsystems.LCD_DISP_PULLUP", "Device:R"},
            {"carrier", "lcd", "R7", "value", "subsystems.LCD_PCLK_DAMPING", "Device:R"},
            {"carrier", "lcd", "C4", "value", "subsystems.LCD_PANEL_BULK", "Device:C"},
            {"carrier", "lcd", "C5", "value", "subsystems.LCD_BOOST_HF", "Device:C"},
            {"carrier", "lcd", "R4", "value", "subsystems.LCD_BLPWM_PULLDOWN", "Device:R"},
            {"carrier", "microsd", "R1", "value", "subsystems.MICROSD_CARD_PULL", "Device:R"},
            {"carrier", "microsd", "R2", "value", "subsystems.MICROSD_CARD_PULL", "Device:R"},
            {"carrier", "microsd", "R3", "value", "subsystems.MICROSD_CARD_PULL", "Device:R"},
            {"carrier", "microsd", "R4", "value", "subsystems.MICROSD_CARD_PULL", "Device:R"},
            {"carrier", "microsd", "R5", "value", "subsystems.MICROSD_CARD_PULL", "Device:R"},
            {"carrier", "microsd", "R6", "value", "subsystems.MICROSD_DETECT_PULL", "Device:R"},
            {"carrier", "microsd", "C1", "value", "subsystems.MICROSD_HOST_BYPASS", "Device:C"},
            {"carrier", "microsd", "C2", "value", "subsystems.MICROSD_CARD_BYPASS", "Device:C"},
            {"carrier", "microsd", "C3", "value", "subsystems.MICROSD_CARD_BULK", "Device:C"},
            {"carrier", "microsd", "C4", "value", "subsystems.MICROSD_ESD_BYPASS", "Device:C"},
            {"carrier", "pd_input", "C1", "value", "subsystems.PD_INPUT_INLET_BYPASS", "Device:C"},
            {"carrier", "pd_input", "R3", "value", "subsystems.PD_INPUT_OVP_TOP", "Device:R"},
            {"carrier", "pd_input", "R4", "value", "subsystems.PD_INPUT_OVP_BOTTOM", "Device:R"},
            {"carrier", "pd_input", "R5", "value", "subsystems.PD_INPUT_ILIM_SET", "Device:R"},
            {"carrier", "pd_input", "C3", "value", "subsystems.PD_INPUT_DVDT_CAP", "Device:C"},
            {"carrier", "pd_input", "R6", "value", "subsystems.PD_INPUT_FAULT_PULL", "Device:R"},
            {"carrier", "pd_input", "C2", "value", "subsystems.PD_INPUT_FUSED_BULK", "Device:C"},
            {"carrier", "pmod", "R1", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"carrier", "pmod", "R2", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"carrier", "pmod", "R3", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"carrier", "pmod", "R4", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"carrier", "pmod", "R5", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"carrier", "pmod", "R6", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"carrier", "pmod", "R7", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"carrier", "pmod", "R8", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"carrier", "pmod", "R9", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"carrier", "pmod", "R10", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"carrier", "pmod", "R11", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"carrier", "pmod", "R12", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"carrier", "pmod", "R13", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"carrier", "pmod", "R14", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"carrier", "pmod", "R15", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"carrier", "pmod", "R16", "value", "subsystems.PMOD_SERIES_DAMPING", "Device:R"},
            {"carrier", "pmod", "C1", "value", "subsystems.PMOD_RAIL_BYPASS", "Device:C"},
            {"carrier", "pmod", "C2", "value", "subsystems.PMOD_RAIL_BULK", "Device:C"},
            {"carrier", "pmod", "C3", "value", "subsystems.PMOD_RAIL_BYPASS", "Device:C"},
            {"carrier", "pmod", "C4", "value", "subsystems.PMOD_RAIL_BULK", "Device:C"},
            {"carrier", "pmod_expansion", "R1", "value", "subsystems.PMOD_EXP_ILIM_SET", "Device:R"},
            {"carrier", "pmod_expansion", "C1", "value", "subsystems.PMOD_EXP_INPUT_BYPASS", "Device:C"},
            {"carrier", "pmod_expansion", "C2", "value", "subsystems.PMOD_EXP_INPUT_BULK", "Device:C"},
            {"carrier", "pmod_expansion", "C3", "value", "subsystems.PMOD_EXP_OUTPUT_BYPASS", "Device:C"},
            {"carrier", "pmod_expansion", "R2", "value", "subsystems.PMOD_EXP_ENABLE_PULLDOWN", "Device:R"},
            {"carrier", "pmod_expansion", "R3", "value", "subsystems.PMOD_EXP_LED_SERIES", "Device:R"},
            {"carrier", "pmod_expansion", "C4", "value", "subsystems.PMOD_EXP_SOCKET_BYPASS", "Device:C"},
            {"carrier", "pmod_expansion", "C5", "value", "subsystems.PMOD_EXP_SOCKET_BULK", "Device:C"},
            {"carrier", "power", "C1", "value", "subsystems.POWER_VIN_HF", "Device:C"},
            {"carrier", "power", "C25", "value", "subsystems.POWER_VIN_HF", "Device:C"},
            {"carrier", "power", "C2", "value", "subsystems.POWER_VIN_BULK", "Device:C"},
            {"carrier", "power", "C3", "value", "subsystems.POWER_VIN_BULK", "Device:C"},
            {"carrier", "power", "C24", "value", "subsystems.POWER_VCC_BYPASS", "Device:C"},
            {"carrier", "power", "R11", "value", "subsystems.POWER_BIAS_SERIES", "Device:R"},
            {"carrier", "power", "C28", "value", "subsystems.POWER_BIAS_BYPASS", "Device:C"},
            {"carrier", "power", "R10", "value", "subsystems.POWER_RT_FREQ", "Device:R"},
            {"carrier", "power", "C4", "value", "subsystems.POWER_BOOT_CAP", "Device:C"},
            {"carrier", "power", "L1", "value", "subsystems.POWER_SW_INDUCTOR", "Device:L"},
            {"carrier", "power", "C5", "value", "subsystems.POWER_COUT_BULK", "Device:C"},
            {"carrier", "power", "C6", "value", "subsystems.POWER_COUT_BULK", "Device:C"},
            {"carrier", "power", "C26", "value", "subsystems.POWER_COUT_BULK", "Device:C"},
            {"carrier", "power", "R1", "value", "subsystems.POWER_FB5V_TOP", "Device:R"},
            {"carrier", "power", "R2", "value", "subsystems.POWER_FB_BOTTOM", "Device:R"},
            {"carrier", "power", "C27", "value", "subsystems.POWER_CFF_CAP", "Device:C"},
            {"carrier", "power", "R12", "value", "subsystems.POWER_RFF_SERIES", "Device:R"},
            {"carrier", "power", "R3", "value", "subsystems.POWER_LED5V_SERIES", "Device:R"},
            {"carrier", "power", "C7", "value", "subsystems.POWER_VIN_HF", "Device:C"},
            {"carrier", "power", "C29", "value", "subsystems.POWER_VIN_HF", "Device:C"},
            {"carrier", "power", "C8", "value", "subsystems.POWER_5V_BULK", "Device:C"},
            {"carrier", "power", "C30", "value", "subsystems.POWER_5V_BULK", "Device:C"},
            {"carrier", "power", "C31", "value", "subsystems.POWER_VCC_BYPASS", "Device:C"},
            {"carrier", "power", "R13", "value", "subsystems.POWER_BIAS_SERIES", "Device:R"},
            {"carrier", "power", "C32", "value", "subsystems.POWER_BIAS_BYPASS", "Device:C"},
            {"carrier", "power", "R14", "value", "subsystems.POWER_RT_FREQ", "Device:R"},
            {"carrier", "power", "C9", "value", "subsystems.POWER_BOOT_CAP", "Device:C"},
            {"carrier", "power", "L2", "value", "subsystems.POWER_SW_INDUCTOR", "Device:L"},
            {"carrier", "power", "C10", "value", "subsystems.POWER_COUT_BULK", "Device:C"},
            {"carrier", "power", "C11", "value", "subsystems.POWER_COUT_BULK", "Device:C"},
            {"carrier", "power", "R4", "value", "subsystems.POWER_FB3V3_TOP", "Device:R"},
            {"carrier", "power", "R5", "value", "subsystems.POWER_FB_BOTTOM", "Device:R"},
            {"carrier", "power", "C23", "value", "subsystems.POWER_CFF_CAP", "Device:C"},
            {"carrier", "power", "R15", "value", "subsystems.POWER_RFF_SERIES", "Device:R"},
            {"carrier", "power", "R6", "value", "subsystems.POWER_LED_SERIES", "Device:R"},
            {"carrier", "power", "C12", "value", "subsystems.POWER_LDO_CAP", "Device:C"},
            {"carrier", "power", "C13", "value", "subsystems.POWER_LDO_CAP", "Device:C"},
            {"carrier", "power", "R7", "value", "subsystems.POWER_GATE_STOP", "Device:R"},
            {"carrier", "power", "R8", "value", "subsystems.POWER_GATE_PULLDOWN", "Device:R"},
            {"carrier", "power", "R9", "value", "subsystems.POWER_LED_SERIES", "Device:R"},
            {"carrier", "rj45_connector", "R1", "value", "subsystems.RJ45_LED_SERIES", "Device:R"},
            {"carrier", "rj45_connector", "R2", "value", "subsystems.RJ45_LED_SERIES", "Device:R"},
            {"carrier", "uart_bridge", "C1", "value", "subsystems.UART_BRIDGE_SUPPLY_BYPASS", "Device:C"},
            {"carrier", "uart_bridge", "C2", "value", "subsystems.UART_BRIDGE_VREGIN_BULK", "Device:C"},
            {"carrier", "uart_bridge", "C3", "value", "subsystems.UART_BRIDGE_SUPPLY_BYPASS", "Device:C"},
            {"carrier", "uart_bridge", "C4", "value", "subsystems.UART_BRIDGE_SUPPLY_BYPASS", "Device:C"},
            {"carrier", "uart_bridge", "R1", "value", "subsystems.UART_BRIDGE_RESET_PULL", "Device:R"},
            {"carrier", "uart_bridge", "R2", "value", "subsystems.UART_BRIDGE_SENSE_TOP", "Device:R"},
            {"carrier", "uart_bridge", "R3", "value", "subsystems.UART_BRIDGE_SENSE_BOTTOM", "Device:R"},
            {"carrier", "usb_jtag", "C1", "value", "subsystems.JTAG_LDO_CIN", "Device:C"},
            {"carrier", "usb_jtag", "C2", "value", "subsystems.JTAG_LDO_COUT", "Device:C"},
            {"carrier", "usb_jtag", "C3", "value", "subsystems.JTAG_SUPPLY_BYPASS", "Device:C"},
            {"carrier", "usb_jtag", "C4", "value", "subsystems.JTAG_SUPPLY_BYPASS", "Device:C"},
            {"carrier", "usb_jtag", "Y1", "value", "subsystems.JTAG_CRYSTAL_FREQ", "1C208000BC0R:1C208000BC0R"},
            {"carrier", "usb_jtag", "C5", "value", "subsystems.JTAG_CRYSTAL_LOAD", "Device:C"},
            {"carrier", "usb_jtag", "C6", "value", "subsystems.JTAG_CRYSTAL_LOAD", "Device:C"},
            {"carrier", "usb_jtag", "R1", "value", "subsystems.JTAG_RESET_PULL", "Device:R"},
            {"carrier", "usb_jtag", "R2", "value", "subsystems.JTAG_MODE_PULLDOWN", "Device:R"},
            {"carrier", "usb_jtag", "R3", "value", "subsystems.JTAG_MODE_PULLDOWN", "Device:R"},
            {"carrier", "usb_jtag", "C7", "value", "subsystems.JTAG_SUPPLY_BYPASS", "Device:C"},
            {"carrier", "usb_jtag", "R4", "value", "subsystems.JTAG_OE_PULLUP", "Device:R"},
            {"carrier", "usb_jtag_connector", "C1", "value", "subsystems.JTAG_CONN_VBUS_BULK", "Device:C"},
            {"carrier", "usb_jtag_connector", "R1", "value", "subsystems.JTAG_CONN_CC_RD", "Device:R"},
            {"carrier", "usb_jtag_connector", "R2", "value", "subsystems.JTAG_CONN_CC_RD", "Device:R"},
            {"carrier", "usb_pd", "C1", "value", "subsystems.USB_PD_VDD_BYPASS", "Device:C"},
            {"carrier", "usb_pd", "C2", "value", "subsystems.USB_PD_VDD_BULK", "Device:C"},
            {"carrier", "usb_pd", "C3", "value", "subsystems.USB_PD_VBUS_BYPASS", "Device:C"},
            {"carrier", "usb_pd", "C4", "value", "subsystems.USB_PD_CC_FILTER", "Device:C"},
            {"carrier", "usb_pd", "C5", "value", "subsystems.USB_PD_CC_FILTER", "Device:C"},
            {"carrier", "usb_uart_connector", "C1", "value", "subsystems.UART_CONN_VBUS_BULK", "Device:C"},
            {"carrier", "usb_uart_connector", "R1", "value", "subsystems.UART_CONN_CC_RD", "Device:R"},
            {"carrier", "usb_uart_connector", "R2", "value", "subsystems.UART_CONN_CC_RD", "Device:R"},
            {"carrier", "usbc_otg", "R5", "value", "subsystems.OTG_ENABLE_PULLDOWN", "Device:R"},
            {"carrier", "usbc_otg", "R3", "value", "subsystems.OTG_FAULT_PULLUP", "Device:R"},
            {"carrier", "usbc_otg", "C1", "value", "subsystems.OTG_INPUT_BYPASS", "Device:C"},
            {"carrier", "usbc_otg", "C2", "value", "subsystems.OTG_VBUS_MLCC", "Device:C"},
            {"carrier", "usbc_otg", "C3", "value", "subsystems.OTG_VBUS_BULK", "RVT1C101M0605_100UF_16V:RVT1C101M0605_100UF_16V"},
            {"carrier", "usbc_otg", "R1", "value", "subsystems.OTG_CC_RP", "Device:R"},
            {"carrier", "usbc_otg", "R2", "value", "subsystems.OTG_CC_RP", "Device:R"},
            {"carrier", "usbc_otg", "R4", "value", "subsystems.OTG_ID_STRAP", "Device:R"},
            {"devkit_mini", "pd_input", "C1", "value", "subsystems.PD_INPUT_INLET_BYPASS", "Device:C"},
            {"devkit_mini", "pd_input", "R3", "value", "subsystems.PD_INPUT_OVP_TOP", "Device:R"},
            {"devkit_mini", "pd_input", "R4", "value", "subsystems.PD_INPUT_OVP_BOTTOM", "Device:R"},
            {"devkit_mini", "pd_input", "R5", "value", "subsystems.PD_INPUT_ILIM_SET", "Device:R"},
            {"devkit_mini", "pd_input", "C3", "value", "subsystems.PD_INPUT_DVDT_CAP", "Device:C"},
            {"devkit_mini", "pd_input", "R6", "value", "subsystems.PD_INPUT_FAULT_PULL", "Device:R"},
            {"devkit_mini", "pd_input", "C2", "value", "subsystems.PD_INPUT_FUSED_BULK", "Device:C"},
            {"devkit_mini", "power", "C1", "value", "subsystems.POWER_VIN_HF", "Device:C"},
            {"devkit_mini", "power", "C25", "value", "subsystems.POWER_VIN_HF", "Device:C"},
            {"devkit_mini", "power", "C2", "value", "subsystems.POWER_VIN_BULK", "Device:C"},
            {"devkit_mini", "power", "C3", "value", "subsystems.POWER_VIN_BULK", "Device:C"},
            {"devkit_mini", "power", "C24", "value", "subsystems.POWER_VCC_BYPASS", "Device:C"},
            {"devkit_mini", "power", "R11", "value", "subsystems.POWER_BIAS_SERIES", "Device:R"},
            {"devkit_mini", "power", "C28", "value", "subsystems.POWER_BIAS_BYPASS", "Device:C"},
            {"devkit_mini", "power", "R10", "value", "subsystems.POWER_RT_FREQ", "Device:R"},
            {"devkit_mini", "power", "C4", "value", "subsystems.POWER_BOOT_CAP", "Device:C"},
            {"devkit_mini", "power", "L1", "value", "subsystems.POWER_SW_INDUCTOR", "Device:L"},
            {"devkit_mini", "power", "C5", "value", "subsystems.POWER_COUT_BULK", "Device:C"},
            {"devkit_mini", "power", "C6", "value", "subsystems.POWER_COUT_BULK", "Device:C"},
            {"devkit_mini", "power", "C26", "value", "subsystems.POWER_COUT_BULK", "Device:C"},
            {"devkit_mini", "power", "R1", "value", "subsystems.POWER_FB5V_TOP", "Device:R"},
            {"devkit_mini", "power", "R2", "value", "subsystems.POWER_FB_BOTTOM", "Device:R"},
            {"devkit_mini", "power", "C27", "value", "subsystems.POWER_CFF_CAP", "Device:C"},
            {"devkit_mini", "power", "R12", "value", "subsystems.POWER_RFF_SERIES", "Device:R"},
            {"devkit_mini", "power", "R3", "value", "subsystems.POWER_LED5V_SERIES", "Device:R"},
            {"devkit_mini", "power", "C7", "value", "subsystems.POWER_VIN_HF", "Device:C"},
            {"devkit_mini", "power", "C29", "value", "subsystems.POWER_VIN_HF", "Device:C"},
            {"devkit_mini", "power", "C8", "value", "subsystems.POWER_5V_BULK", "Device:C"},
            {"devkit_mini", "power", "C30", "value", "subsystems.POWER_5V_BULK", "Device:C"},
            {"devkit_mini", "power", "C31", "value", "subsystems.POWER_VCC_BYPASS", "Device:C"},
            {"devkit_mini", "power", "R13", "value", "subsystems.POWER_BIAS_SERIES", "Device:R"},
            {"devkit_mini", "power", "C32", "value", "subsystems.POWER_BIAS_BYPASS", "Device:C"},
            {"devkit_mini", "power", "R14", "value", "subsystems.POWER_RT_FREQ", "Device:R"},
            {"devkit_mini", "power", "C9", "value", "subsystems.POWER_BOOT_CAP", "Device:C"},
            {"devkit_mini", "power", "L2", "value", "subsystems.POWER_SW_INDUCTOR", "Device:L"},
            {"devkit_mini", "power", "C10", "value", "subsystems.POWER_COUT_BULK", "Device:C"},
            {"devkit_mini", "power", "C11", "value", "subsystems.POWER_COUT_BULK", "Device:C"},
            {"devkit_mini", "power", "R4", "value", "subsystems.POWER_FB3V3_TOP", "Device:R"},
            {"devkit_mini", "power", "R5", "value", "subsystems.POWER_FB_BOTTOM", "Device:R"},
            {"devkit_mini", "power", "C23", "value", "subsystems.POWER_CFF_CAP", "Device:C"},
            {"devkit_mini", "power", "R15", "value", "subsystems.POWER_RFF_SERIES", "Device:R"},
            {"devkit_mini", "power", "R6", "value", "subsystems.POWER_LED_SERIES", "Device:R"},
            {"devkit_mini", "power", "C12", "value", "subsystems.POWER_LDO_CAP", "Device:C"},
            {"devkit_mini", "power", "C13", "value", "subsystems.POWER_LDO_CAP", "Device:C"},
            {"devkit_mini", "power", "R7", "value", "subsystems.POWER_GATE_STOP", "Device:R"},
            {"devkit_mini", "power", "R8", "value", "subsystems.POWER_GATE_PULLDOWN", "Device:R"},
            {"devkit_mini", "power", "R9", "value", "subsystems.POWER_LED_SERIES", "Device:R"},
            {"devkit_mini", "uart_bridge", "C1", "value", "subsystems.UART_BRIDGE_SUPPLY_BYPASS", "Device:C"},
            {"devkit_mini", "uart_bridge", "C2", "value", "subsystems.UART_BRIDGE_VREGIN_BULK", "Device:C"},
            {"devkit_mini", "uart_bridge", "C3", "value", "subsystems.UART_BRIDGE_SUPPLY_BYPASS", "Device:C"},
            {"devkit_mini", "uart_bridge", "C4", "value", "subsystems.UART_BRIDGE_SUPPLY_BYPASS", "Device:C"},
            {"devkit_mini", "uart_bridge", "R1", "value", "subsystems.UART_BRIDGE_RESET_PULL", "Device:R"},
            {"devkit_mini", "uart_bridge", "R2", "value", "subsystems.UART_BRIDGE_SENSE_TOP", "Device:R"},
            {"devkit_mini", "uart_bridge", "R3", "value", "subsystems.UART_BRIDGE_SENSE_BOTTOM", "Device:R"},
            {"devkit_mini", "usb_uart_connector", "C1", "value", "subsystems.UART_CONN_VBUS_BULK", "Device:C"},
            {"devkit_mini", "usb_uart_connector", "R1", "value", "subsystems.UART_CONN_CC_RD", "Device:R"},
            {"devkit_mini", "usb_uart_connector", "R2", "value", "subsystems.UART_CONN_CC_RD", "Device:R"},
        };
        p.sheets = {
            {"library", "camera"},
            {"library", "ethernet"},
            {"library", "hdmi_rx"},
            {"library", "hdmi_tx"},
            {"library", "lcd"},
            {"library", "microsd"},
            {"library", "pd_input"},
            {"library", "pmod"},
            {"library", "pmod_expansion"},
            {"library", "power"},
            {"library", "rj45_connector"},
            {"library", "uart_bridge"},
            {"library", "usb_jtag"},
            {"library", "usb_jtag_connector"},
            {"library", "usb_pd"},
            {"library", "usb_uart_connector"},
            {"library", "usbc_otg"},
            {"carrier", "board_aux"},
            {"carrier", "board_qwiic"},
            {"carrier", "board_services"},
            {"carrier", "bringup_en"},
            {"carrier", "bringup_en_modules"},
            {"carrier", "bringup_modules"},
            {"carrier", "bringup_rails"},
            {"carrier", "camera"},
            {"carrier", "debug_boot"},
            {"carrier", "ethernet"},
            {"carrier", "fmc"},
            {"carrier", "hdmi_rx"},
            {"carrier", "hdmi_rx_term"},
            {"carrier", "hdmi_tx"},
            {"carrier", "lcd"},
            {"carrier", "mechanical"},
            {"carrier", "microsd"},
            {"carrier", "motor_pwm"},
            {"carrier", "motor_sense"},
            {"carrier", "pd_input"},
            {"carrier", "pmod"},
            {"carrier", "pmod_expansion"},
            {"carrier", "power"},
            {"carrier", "power_mon"},
            {"carrier", "power_som"},
            {"carrier", "rj45_connector"},
            {"carrier", "som_decoupling"},
            {"carrier", "som_j1"},
            {"carrier", "som_j2"},
            {"carrier", "som_j3"},
            {"carrier", "uart_bridge"},
            {"carrier", "usb_jtag"},
            {"carrier", "usb_jtag_connector"},
            {"carrier", "usb_pd"},
            {"carrier", "usb_uart_connector"},
            {"carrier", "usbc_otg"},
            {"carrier", "user_io"},
            {"devkit_mini", "debug_boot"},
            {"devkit_mini", "mechanical"},
            {"devkit_mini", "pd_input"},
            {"devkit_mini", "power"},
            {"devkit_mini", "power_mon"},
            {"devkit_mini", "power_som"},
            {"devkit_mini", "som_decoupling"},
            {"devkit_mini", "som_j1"},
            {"devkit_mini", "som_j2"},
            {"devkit_mini", "som_j3"},
            {"devkit_mini", "uart_bridge"},
            {"devkit_mini", "usb_uart_connector"},
        };
        return p;
    }();
    return policy;
}
} // namespace schgen
