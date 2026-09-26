#include "schgen/subsystem_authoring.hpp"
#include "schgen/subsystem_registration.hpp"

namespace schgen {
namespace subsystem_builders {
CircuitSheetIr camera(const SubsystemMeta&, const AuthoringContext&);
CircuitSheetIr ethernet(const SubsystemMeta&, const AuthoringContext&);
CircuitSheetIr hdmi_rx(const SubsystemMeta&, const AuthoringContext&);
CircuitSheetIr hdmi_tx(const SubsystemMeta&, const AuthoringContext&);
CircuitSheetIr lcd(const SubsystemMeta&, const AuthoringContext&);
CircuitSheetIr microsd(const SubsystemMeta&, const AuthoringContext&);
CircuitSheetIr pd_input(const SubsystemMeta&, const AuthoringContext&);
CircuitSheetIr pmod(const SubsystemMeta&, const AuthoringContext&);
CircuitSheetIr pmod_expansion(const SubsystemMeta&, const AuthoringContext&);
CircuitSheetIr power(const SubsystemMeta&, const AuthoringContext&);
CircuitSheetIr rj45_connector(const SubsystemMeta&, const AuthoringContext&);
CircuitSheetIr uart_bridge(const SubsystemMeta&, const AuthoringContext&);
CircuitSheetIr usb_jtag(const SubsystemMeta&, const AuthoringContext&);
CircuitSheetIr usb_jtag_connector(const SubsystemMeta&, const AuthoringContext&);
CircuitSheetIr usb_pd(const SubsystemMeta&, const AuthoringContext&);
CircuitSheetIr usb_uart_connector(const SubsystemMeta&, const AuthoringContext&);
CircuitSheetIr usbc_otg(const SubsystemMeta&, const AuthoringContext&);
}
const std::vector<SubsystemDefinition>& subsystem_definitions() {
    static const std::vector<SubsystemDefinition> definitions = append_configured_subsystem_definitions({
        {"camera", {"+VDD_CAM", "GND", "CSI_D0_P", "CSI_D0_N", "CSI_D1_P", "CSI_D1_N", "CSI_CLK_P", "CSI_CLK_N", "CAM_SCL", "CAM_SDA", "CAM_EN", "CAM_LED"}, subsystem_builders::camera},
        {"ethernet", {"CHASSIS_GND", "MDI0_P", "MDI0_N", "MDI1_P", "MDI1_N", "MDI2_P", "MDI2_N", "MDI3_P", "MDI3_N", "MX0_P", "MX0_N", "MX1_P", "MX1_N", "MX2_P", "MX2_N", "MX3_P", "MX3_N"}, subsystem_builders::ethernet},
        {"hdmi_rx", {"+VDD_LOGIC", "GND", "CHASSIS_GND", "TMDS_RX_D2_P", "TMDS_RX_D2_N", "TMDS_RX_D1_P", "TMDS_RX_D1_N", "TMDS_RX_D0_P", "TMDS_RX_D0_N", "TMDS_RX_CLK_P", "TMDS_RX_CLK_N", "HDMI_5V_DET", "CEC"}, subsystem_builders::hdmi_rx},
        {"hdmi_tx", {"+VDD_IO", "+5V", "GND", "CHASSIS_GND", "TMDS_D2_P", "TMDS_D2_N", "TMDS_D1_P", "TMDS_D1_N", "TMDS_D0_P", "TMDS_D0_N", "TMDS_CLK_P", "TMDS_CLK_N", "CEC", "DDC_SCL", "DDC_SDA", "HPD"}, subsystem_builders::hdmi_tx},
        {"lcd", {"+VBOOST_IN", "+VDD_LCD", "+VDD_TP_CLAMP", "GND", "LCD_R0", "LCD_R1", "LCD_R2", "LCD_R3", "LCD_R4", "LCD_R5", "LCD_R6", "LCD_R7", "LCD_G0", "LCD_G1", "LCD_G2", "LCD_G3", "LCD_G4", "LCD_G5", "LCD_G6", "LCD_G7", "LCD_B0", "LCD_B1", "LCD_B2", "LCD_B3", "LCD_B4", "LCD_B5", "LCD_B6", "LCD_B7", "LCD_DISP", "LCD_HSYNC", "LCD_VSYNC", "LCD_DE", "TP_SDA", "TP_SCL", "TP_RST", "TP_INT", "LCD_PCLK", "BL_PWM"}, subsystem_builders::lcd},
        {"microsd", {"+VDD_HOST", "+VDD_CARD", "GND", "SD_CLK", "SD_CMD", "SD_D0", "SD_D1", "SD_D2", "SD_D3", "CD_N"}, subsystem_builders::microsd},
        {"pd_input", {"+VBUS_CONN", "+VBUS_OUT", "+VDD_LOGIC", "GND", "CHASSIS_GND", "CC1", "CC2", "USB_D_P", "USB_D_N", "FLT_N"}, subsystem_builders::pd_input},
        {"pmod", {"+VCC_PMOD", "GND", "PMOD0_SIG1", "PMOD0_SIG2", "PMOD0_SIG3", "PMOD0_SIG4", "PMOD0_SIG5", "PMOD0_SIG6", "PMOD0_SIG7", "PMOD0_SIG8", "PMOD1_SIG1", "PMOD1_SIG2", "PMOD1_SIG3", "PMOD1_SIG4", "PMOD1_SIG5", "PMOD1_SIG6", "PMOD1_SIG7", "PMOD1_SIG8"}, subsystem_builders::pmod},
        {"pmod_expansion", {"+VDD_PMOD", "+VSW_PMOD", "GND", "PMOD_IO1", "PMOD_IO2", "PMOD_IO3", "PMOD_IO4", "PMOD_IO5", "PMOD_IO6", "PMOD_IO7", "PMOD_IO8"}, subsystem_builders::pmod_expansion},
        {"power", {"+VIN", "+VOUT_5V_REG", "+VOUT_5V", "+VOUT_3V3_REG", "+VOUT_3V3", "+VOUT_1V8_REG", "+VOUT_1V8", "GND", "EN_VOUT_5V", "EN_VOUT_3V3", "EN_VOUT_1V8"}, subsystem_builders::power},
        {"rj45_connector", {"+VLED", "GND", "CHASSIS_GND", "RJ45_MDI0_P", "RJ45_MDI0_N", "RJ45_MDI1_P", "RJ45_MDI1_N", "RJ45_MDI2_P", "RJ45_MDI2_N", "RJ45_MDI3_P", "RJ45_MDI3_N"}, subsystem_builders::rj45_connector},
        {"uart_bridge", {"+VDD_IO", "GND", "USB_VBUS", "USB_DP", "USB_DM", "UART_TXD", "UART_RXD", "UART_RTS_N", "UART_CTS_N"}, subsystem_builders::uart_bridge},
        {"usb_jtag", {"+VBUS_USB", "+3V3_ISLAND", "GND", "USB_DP", "USB_DM", "JTAG_TCK", "JTAG_TDI", "JTAG_TMS", "JTAG_TDO", "UART_RXD", "UART_TXD"}, subsystem_builders::usb_jtag},
        {"usb_jtag_connector", {"+VBUS", "GND", "CHASSIS_GND", "USB_DP", "USB_DM"}, subsystem_builders::usb_jtag_connector},
        {"usb_pd", {"+VDD_LOGIC", "+VBUS_SENSE", "GND", "CC1", "CC2", "I2C_SDA", "I2C_SCL", "INT_N"}, subsystem_builders::usb_pd},
        {"usb_uart_connector", {"GND", "CHASSIS_GND", "VBUS", "USB_DP", "USB_DM"}, subsystem_builders::usb_uart_connector},
        {"usbc_otg", {"+VBUS_SUPPLY", "+VDD_LOGIC", "GND", "CHASSIS_GND", "USB_DP", "USB_DM", "VBUS", "VBUS_EN", "FLT_N", "USB_ID"}, subsystem_builders::usbc_otg},
    });
    return definitions;
}
const SubsystemDefinition& subsystem_definition(const std::string& name) {
    for (const auto& d : subsystem_definitions()) if (d.name == name) return d;
    throw CircuitAuthoringError("unknown subsystem " + name);
}
CircuitSheetIr author_subsystem(const std::string& name, const SubsystemMeta& meta, const AuthoringContext& context) {
    return subsystem_definition(name).circuit(meta, context);
}
} // namespace schgen
