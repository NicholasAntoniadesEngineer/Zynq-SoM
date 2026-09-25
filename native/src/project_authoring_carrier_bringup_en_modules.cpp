#include "schgen/subsystem_authoring.hpp"

namespace schgen::project_builders {
// Migrated construction operations from carrier/subsystems/bringup_en_modules/bringup_en_modules.py.
CircuitSheetIr carrier_bringup_en_modules(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("bringup_en_modules", "Bring-up EN cells: 11x SN74LVC1G08 module DIP-AND-override", context);
    c.part("U1", "74xGxx:74LVC1G08", "SN74LVC1G08", "Package_TO_SOT_SMD:SOT-23-5", {{"LCSC", "C7666"}});
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_DIP_HDMI_TX", {"U1.1"}, t, true);
    }
    c.auto_ref("R");
    c.part("R1", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("BU_DIP_HDMI_TX", {"R1.1"}, std::nullopt);
    c.net("GND", {"R1.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_OVR_HDMI_TX", {"U1.2"}, t, true);
    }
    c.pullup("U1.2", "100k", "+3V3_SC", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    {
        AuthoringPort t;
        t.expect = "bringup_modules (SY6280 load-switch cells)";
        c.port("EN_HDMI_TX", {"U1.4"}, t, true);
    }
    c.net("+3V3_SC", {"U1.5"}, std::nullopt);
    c.net("GND", {"U1.3"}, std::nullopt);
    c.decouple("U1.5", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.part("U2", "74xGxx:74LVC1G08", "SN74LVC1G08", "Package_TO_SOT_SMD:SOT-23-5", {{"LCSC", "C7666"}});
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_DIP_HDMI_RX", {"U2.1"}, t, true);
    }
    c.auto_ref("R");
    c.part("R3", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("BU_DIP_HDMI_RX", {"R3.1"}, std::nullopt);
    c.net("GND", {"R3.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_OVR_HDMI_RX", {"U2.2"}, t, true);
    }
    c.pullup("U2.2", "100k", "+3V3_SC", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    {
        AuthoringPort t;
        t.expect = "bringup_modules (SY6280 load-switch cells)";
        c.port("EN_HDMI_RX", {"U2.4"}, t, true);
    }
    c.net("+3V3_SC", {"U2.5"}, std::nullopt);
    c.net("GND", {"U2.3"}, std::nullopt);
    c.decouple("U2.5", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.part("U3", "74xGxx:74LVC1G08", "SN74LVC1G08", "Package_TO_SOT_SMD:SOT-23-5", {{"LCSC", "C7666"}});
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_DIP_LCD", {"U3.1"}, t, true);
    }
    c.auto_ref("R");
    c.part("R5", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("BU_DIP_LCD", {"R5.1"}, std::nullopt);
    c.net("GND", {"R5.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_OVR_LCD", {"U3.2"}, t, true);
    }
    c.pullup("U3.2", "100k", "+3V3_SC", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    {
        AuthoringPort t;
        t.expect = "bringup_modules (SY6280 load-switch cells)";
        c.port("EN_LCD", {"U3.4"}, t, true);
    }
    c.net("+3V3_SC", {"U3.5"}, std::nullopt);
    c.net("GND", {"U3.3"}, std::nullopt);
    c.decouple("U3.5", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.part("U4", "74xGxx:74LVC1G08", "SN74LVC1G08", "Package_TO_SOT_SMD:SOT-23-5", {{"LCSC", "C7666"}});
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_DIP_CAM", {"U4.1"}, t, true);
    }
    c.auto_ref("R");
    c.part("R7", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("BU_DIP_CAM", {"R7.1"}, std::nullopt);
    c.net("GND", {"R7.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_OVR_CAM", {"U4.2"}, t, true);
    }
    c.pullup("U4.2", "100k", "+3V3_SC", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    {
        AuthoringPort t;
        t.expect = "bringup_modules (SY6280 load-switch cells)";
        c.port("EN_CAM", {"U4.4"}, t, true);
    }
    c.net("+3V3_SC", {"U4.5"}, std::nullopt);
    c.net("GND", {"U4.3"}, std::nullopt);
    c.decouple("U4.5", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.part("U5", "74xGxx:74LVC1G08", "SN74LVC1G08", "Package_TO_SOT_SMD:SOT-23-5", {{"LCSC", "C7666"}});
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_DIP_SD", {"U5.1"}, t, true);
    }
    c.auto_ref("R");
    c.part("R9", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("BU_DIP_SD", {"R9.1"}, std::nullopt);
    c.net("GND", {"R9.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_OVR_SD", {"U5.2"}, t, true);
    }
    c.pullup("U5.2", "100k", "+3V3_SC", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    {
        AuthoringPort t;
        t.expect = "bringup_modules (SY6280 load-switch cells)";
        c.port("EN_SD", {"U5.4"}, t, true);
    }
    c.net("+3V3_SC", {"U5.5"}, std::nullopt);
    c.net("GND", {"U5.3"}, std::nullopt);
    c.decouple("U5.5", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.part("U6", "74xGxx:74LVC1G08", "SN74LVC1G08", "Package_TO_SOT_SMD:SOT-23-5", {{"LCSC", "C7666"}});
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_DIP_USB", {"U6.1"}, t, true);
    }
    c.auto_ref("R");
    c.part("R11", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("BU_DIP_USB", {"R11.1"}, std::nullopt);
    c.net("GND", {"R11.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_OVR_USB", {"U6.2"}, t, true);
    }
    c.pullup("U6.2", "100k", "+3V3_SC", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    {
        AuthoringPort t;
        t.expect = "bringup_modules (SY6280 load-switch cells)";
        c.port("EN_USB", {"U6.4"}, t, true);
    }
    c.net("+3V3_SC", {"U6.5"}, std::nullopt);
    c.net("GND", {"U6.3"}, std::nullopt);
    c.decouple("U6.5", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.part("U7", "74xGxx:74LVC1G08", "SN74LVC1G08", "Package_TO_SOT_SMD:SOT-23-5", {{"LCSC", "C7666"}});
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_DIP_PMOD", {"U7.1"}, t, true);
    }
    c.auto_ref("R");
    c.part("R13", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("BU_DIP_PMOD", {"R13.1"}, std::nullopt);
    c.net("GND", {"R13.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_OVR_PMOD", {"U7.2"}, t, true);
    }
    c.pullup("U7.2", "100k", "+3V3_SC", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    {
        AuthoringPort t;
        t.expect = "bringup_modules (SY6280 load-switch cells)";
        c.port("EN_PMOD", {"U7.4"}, t, true);
    }
    c.net("+3V3_SC", {"U7.5"}, std::nullopt);
    c.net("GND", {"U7.3"}, std::nullopt);
    c.decouple("U7.5", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.part("U8", "74xGxx:74LVC1G08", "SN74LVC1G08", "Package_TO_SOT_SMD:SOT-23-5", {{"LCSC", "C7666"}});
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_DIP_USER_LED", {"U8.1"}, t, true);
    }
    c.auto_ref("R");
    c.part("R15", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("BU_DIP_USER_LED", {"R15.1"}, std::nullopt);
    c.net("GND", {"R15.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_OVR_USER_LED", {"U8.2"}, t, true);
    }
    c.pullup("U8.2", "100k", "+3V3_SC", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    {
        AuthoringPort t;
        t.expect = "bringup_modules (SY6280 load-switch cells)";
        c.port("EN_USER_LED", {"U8.4"}, t, true);
    }
    c.net("+3V3_SC", {"U8.5"}, std::nullopt);
    c.net("GND", {"U8.3"}, std::nullopt);
    c.decouple("U8.5", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.part("U9", "74xGxx:74LVC1G08", "SN74LVC1G08", "Package_TO_SOT_SMD:SOT-23-5", {{"LCSC", "C7666"}});
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_DIP_SPARE", {"U9.1"}, t, true);
    }
    c.auto_ref("R");
    c.part("R17", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("BU_DIP_SPARE", {"R17.1"}, std::nullopt);
    c.net("GND", {"R17.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_OVR_LCD_BL", {"U9.2"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "RESERVED gated-EN hook (EN_LCD_BL -> testpoint; backlight is PWM-direct)";
        c.port("EN_LCD_BL", {"U9.4"}, t, true);
    }
    c.net("+3V3_SC", {"U9.5"}, std::nullopt);
    c.net("GND", {"U9.3"}, std::nullopt);
    c.decouple("U9.5", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.part("U10", "74xGxx:74LVC1G08", "SN74LVC1G08", "Package_TO_SOT_SMD:SOT-23-5", {{"LCSC", "C7666"}});
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_DIP_HDMI_TX_5V", {"U10.1"}, t, true);
    }
    c.auto_ref("R");
    c.part("R18", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("BU_DIP_HDMI_TX_5V", {"R18.1"}, std::nullopt);
    c.net("GND", {"R18.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_OVR_HDMI_TX_5V", {"U10.2"}, t, true);
    }
    c.pullup("U10.2", "100k", "+3V3_SC", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    {
        AuthoringPort t;
        t.expect = "bringup_modules (SY6280 load-switch cells)";
        c.port("EN_HDMI_TX_5V", {"U10.4"}, t, true);
    }
    c.net("+3V3_SC", {"U10.5"}, std::nullopt);
    c.net("GND", {"U10.3"}, std::nullopt);
    c.decouple("U10.5", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.part("U11", "74xGxx:74LVC1G08", "SN74LVC1G08", "Package_TO_SOT_SMD:SOT-23-5", {{"LCSC", "C7666"}});
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_DIP_LCD_5V", {"U11.1"}, t, true);
    }
    c.auto_ref("R");
    c.part("R20", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("BU_DIP_LCD_5V", {"R20.1"}, std::nullopt);
    c.net("GND", {"R20.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_OVR_LCD_5V", {"U11.2"}, t, true);
    }
    c.pullup("U11.2", "100k", "+3V3_SC", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    {
        AuthoringPort t;
        t.expect = "bringup_modules (SY6280 load-switch cells)";
        c.port("EN_LCD_5V", {"U11.4"}, t, true);
    }
    c.net("+3V3_SC", {"U11.5"}, std::nullopt);
    c.net("GND", {"U11.3"}, std::nullopt);
    c.decouple("U11.5", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.testpoint("EN_HDMI_TX", std::nullopt);
    c.testpoint("EN_HDMI_RX", std::nullopt);
    c.testpoint("EN_LCD", std::nullopt);
    c.testpoint("EN_CAM", std::nullopt);
    c.testpoint("EN_SD", std::nullopt);
    c.testpoint("EN_USB", std::nullopt);
    c.testpoint("EN_PMOD", std::nullopt);
    c.testpoint("EN_USER_LED", std::nullopt);
    c.testpoint("EN_LCD_BL", std::nullopt);
    c.testpoint("EN_HDMI_TX_5V", std::nullopt);
    c.testpoint("EN_LCD_5V", std::nullopt);
    c.draws("+3V3_SC", 0.005, "11x SN74LVC1G08 + 100k pull networks");
    c.field("R2", "LCSC", "C25803");
    c.field("C1", "LCSC", "C14663");
    c.field("R4", "LCSC", "C25803");
    c.field("C2", "LCSC", "C14663");
    c.field("R6", "LCSC", "C25803");
    c.field("C3", "LCSC", "C14663");
    c.field("R8", "LCSC", "C25803");
    c.field("C4", "LCSC", "C14663");
    c.field("R10", "LCSC", "C25803");
    c.field("C5", "LCSC", "C14663");
    c.field("R12", "LCSC", "C25803");
    c.field("C6", "LCSC", "C14663");
    c.field("R14", "LCSC", "C25803");
    c.field("C7", "LCSC", "C14663");
    c.field("R16", "LCSC", "C25803");
    c.field("C8", "LCSC", "C14663");
    c.field("C9", "LCSC", "C14663");
    c.field("R19", "LCSC", "C25803");
    c.field("C10", "LCSC", "C14663");
    c.field("R21", "LCSC", "C25803");
    c.field("C11", "LCSC", "C14663");
    return meta.finish(c);
}
} // namespace schgen::project_builders
