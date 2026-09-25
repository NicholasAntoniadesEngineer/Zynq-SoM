#include "schgen/subsystem_authoring.hpp"

namespace schgen::project_builders {
// Migrated construction operations from carrier/subsystems/bringup_modules/bringup_modules.py.
CircuitSheetIr carrier_bringup_modules(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("bringup_modules", "Bring-up module gates: 10x SY6280 + status/user LEDs", context);
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        c.use_part("SY6280AAC", p);
    }
    c.net("+3V3", {"U1.IN"}, std::nullopt);
    c.net("+3V3_HDMI_TX", {"U1.OUT"}, std::nullopt);
    c.net("GND", {"U1.GND"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.2)";
        c.port("EN_HDMI_TX", {"U1.EN"}, t, true);
    }
    c.auto_ref("R");
    c.part("R1", "Device:R", "13k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22797"}});
    c.net("BU_ISET_HDMI_TX", {"U1.ISET", "R1.1"}, std::nullopt);
    c.net("GND", {"R1.2"}, std::nullopt);
    c.decouple("U1.IN", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.decouple("U1.OUT", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.auto_ref("D");
    c.part("D1", "Device:LED", "red", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C2286"}});
    c.auto_ref("R");
    c.part("R2", "Device:R", "330R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23138"}});
    c.net("+3V3_HDMI_TX", {"D1.2"}, std::nullopt);
    c.net("BU_PG_HDMI_TX", {"D1.1", "R2.1"}, std::nullopt);
    c.net("GND", {"R2.2"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "U2";
        c.use_part("SY6280AAC", p);
    }
    c.net("+3V3", {"U2.IN"}, std::nullopt);
    c.net("+3V3_HDMI_RX", {"U2.OUT"}, std::nullopt);
    c.net("GND", {"U2.GND"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.2)";
        c.port("EN_HDMI_RX", {"U2.EN"}, t, true);
    }
    c.auto_ref("R");
    c.part("R3", "Device:R", "13k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22797"}});
    c.net("BU_ISET_HDMI_RX", {"U2.ISET", "R3.1"}, std::nullopt);
    c.net("GND", {"R3.2"}, std::nullopt);
    c.decouple("U2.IN", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.decouple("U2.OUT", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.auto_ref("D");
    c.part("D2", "Device:LED", "red", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C2286"}});
    c.auto_ref("R");
    c.part("R4", "Device:R", "330R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23138"}});
    c.net("+3V3_HDMI_RX", {"D2.2"}, std::nullopt);
    c.net("BU_PG_HDMI_RX", {"D2.1", "R4.1"}, std::nullopt);
    c.net("GND", {"R4.2"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "U3";
        c.use_part("SY6280AAC", p);
    }
    c.net("+3V3", {"U3.IN"}, std::nullopt);
    c.net("+3V3_LCD", {"U3.OUT"}, std::nullopt);
    c.net("GND", {"U3.GND"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.2)";
        c.port("EN_LCD", {"U3.EN"}, t, true);
    }
    c.auto_ref("R");
    c.part("R5", "Device:R", "6.8k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23212"}});
    c.net("BU_ISET_LCD", {"U3.ISET", "R5.1"}, std::nullopt);
    c.net("GND", {"R5.2"}, std::nullopt);
    c.decouple("U3.IN", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.decouple("U3.OUT", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.auto_ref("D");
    c.part("D3", "Device:LED", "red", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C2286"}});
    c.auto_ref("R");
    c.part("R6", "Device:R", "330R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23138"}});
    c.net("+3V3_LCD", {"D3.2"}, std::nullopt);
    c.net("BU_PG_LCD", {"D3.1", "R6.1"}, std::nullopt);
    c.net("GND", {"R6.2"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "U4";
        c.use_part("SY6280AAC", p);
    }
    c.net("+3V3", {"U4.IN"}, std::nullopt);
    c.net("+3V3_CAM", {"U4.OUT"}, std::nullopt);
    c.net("GND", {"U4.GND"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.2)";
        c.port("EN_CAM", {"U4.EN"}, t, true);
    }
    c.auto_ref("R");
    c.part("R7", "Device:R", "13k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22797"}});
    c.net("BU_ISET_CAM", {"U4.ISET", "R7.1"}, std::nullopt);
    c.net("GND", {"R7.2"}, std::nullopt);
    c.decouple("U4.IN", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.decouple("U4.OUT", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.auto_ref("D");
    c.part("D4", "Device:LED", "red", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C2286"}});
    c.auto_ref("R");
    c.part("R8", "Device:R", "330R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23138"}});
    c.net("+3V3_CAM", {"D4.2"}, std::nullopt);
    c.net("BU_PG_CAM", {"D4.1", "R8.1"}, std::nullopt);
    c.net("GND", {"R8.2"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "U5";
        c.use_part("SY6280AAC", p);
    }
    c.net("+3V3", {"U5.IN"}, std::nullopt);
    c.net("+3V3_SD", {"U5.OUT"}, std::nullopt);
    c.net("GND", {"U5.GND"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.2)";
        c.port("EN_SD", {"U5.EN"}, t, true);
    }
    c.auto_ref("R");
    c.part("R9", "Device:R", "6.8k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23212"}});
    c.net("BU_ISET_SD", {"U5.ISET", "R9.1"}, std::nullopt);
    c.net("GND", {"R9.2"}, std::nullopt);
    c.decouple("U5.IN", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.decouple("U5.OUT", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.auto_ref("D");
    c.part("D5", "Device:LED", "red", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C2286"}});
    c.auto_ref("R");
    c.part("R10", "Device:R", "330R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23138"}});
    c.net("+3V3_SD", {"D5.2"}, std::nullopt);
    c.net("BU_PG_SD", {"D5.1", "R10.1"}, std::nullopt);
    c.net("GND", {"R10.2"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "U6";
        c.use_part("SY6280AAC", p);
    }
    c.net("+5V", {"U6.IN"}, std::nullopt);
    c.net("+5V_USB", {"U6.OUT"}, std::nullopt);
    c.net("GND", {"U6.GND"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.2)";
        c.port("EN_USB", {"U6.EN"}, t, true);
    }
    c.auto_ref("R");
    c.part("R11", "Device:R", "6.8k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23212"}});
    c.net("BU_ISET_USB", {"U6.ISET", "R11.1"}, std::nullopt);
    c.net("GND", {"R11.2"}, std::nullopt);
    c.decouple("U6.IN", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.decouple("U6.OUT", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.auto_ref("D");
    c.part("D6", "Device:LED", "red", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C2286"}});
    c.auto_ref("R");
    c.part("R12", "Device:R", "1k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C21190"}});
    c.net("+5V_USB", {"D6.2"}, std::nullopt);
    c.net("BU_PG_USB", {"D6.1", "R12.1"}, std::nullopt);
    c.net("GND", {"R12.2"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "U7";
        c.use_part("SY6280AAC", p);
    }
    c.net("+3V3", {"U7.IN"}, std::nullopt);
    c.net("+3V3_PMOD", {"U7.OUT"}, std::nullopt);
    c.net("GND", {"U7.GND"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.2)";
        c.port("EN_PMOD", {"U7.EN"}, t, true);
    }
    c.auto_ref("R");
    c.part("R13", "Device:R", "13k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22797"}});
    c.net("BU_ISET_PMOD", {"U7.ISET", "R13.1"}, std::nullopt);
    c.net("GND", {"R13.2"}, std::nullopt);
    c.decouple("U7.IN", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.decouple("U7.OUT", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.auto_ref("D");
    c.part("D7", "Device:LED", "red", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C2286"}});
    c.auto_ref("R");
    c.part("R14", "Device:R", "330R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23138"}});
    c.net("+3V3_PMOD", {"D7.2"}, std::nullopt);
    c.net("BU_PG_PMOD", {"D7.1", "R14.1"}, std::nullopt);
    c.net("GND", {"R14.2"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "U8";
        c.use_part("SY6280AAC", p);
    }
    c.net("+3V3", {"U8.IN"}, std::nullopt);
    c.net("+3V3_USER_LED", {"U8.OUT"}, std::nullopt);
    c.net("GND", {"U8.GND"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.2)";
        c.port("EN_USER_LED", {"U8.EN"}, t, true);
    }
    c.auto_ref("R");
    c.part("R15", "Device:R", "13k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22797"}});
    c.net("BU_ISET_USER_LED", {"U8.ISET", "R15.1"}, std::nullopt);
    c.net("GND", {"R15.2"}, std::nullopt);
    c.decouple("U8.IN", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.decouple("U8.OUT", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.auto_ref("D");
    c.part("D8", "Device:LED", "red", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C2286"}});
    c.auto_ref("R");
    c.part("R16", "Device:R", "330R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23138"}});
    c.net("+3V3_USER_LED", {"D8.2"}, std::nullopt);
    c.net("BU_PG_USER_LED", {"D8.1", "R16.1"}, std::nullopt);
    c.net("GND", {"R16.2"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "U9";
        c.use_part("SY6280AAC", p);
    }
    c.net("+5V", {"U9.IN"}, std::nullopt);
    c.net("+5V_HDMI_TX", {"U9.OUT"}, std::nullopt);
    c.net("GND", {"U9.GND"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.2)";
        c.port("EN_HDMI_TX_5V", {"U9.EN"}, t, true);
    }
    c.auto_ref("R");
    c.part("R17", "Device:R", "13k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22797"}});
    c.net("BU_ISET_HDMI_TX_5V", {"U9.ISET", "R17.1"}, std::nullopt);
    c.net("GND", {"R17.2"}, std::nullopt);
    c.decouple("U9.IN", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.decouple("U9.OUT", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.auto_ref("D");
    c.part("D9", "Device:LED", "red", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C2286"}});
    c.auto_ref("R");
    c.part("R18", "Device:R", "1k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C21190"}});
    c.net("+5V_HDMI_TX", {"D9.2"}, std::nullopt);
    c.net("BU_PG_HDMI_TX_5V", {"D9.1", "R18.1"}, std::nullopt);
    c.net("GND", {"R18.2"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "U10";
        c.use_part("SY6280AAC", p);
    }
    c.net("+5V", {"U10.IN"}, std::nullopt);
    c.net("+5V_LCD", {"U10.OUT"}, std::nullopt);
    c.net("GND", {"U10.GND"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.2)";
        c.port("EN_LCD_5V", {"U10.EN"}, t, true);
    }
    c.auto_ref("R");
    c.part("R19", "Device:R", "6.8k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23212"}});
    c.net("BU_ISET_LCD_5V", {"U10.ISET", "R19.1"}, std::nullopt);
    c.net("GND", {"R19.2"}, std::nullopt);
    c.decouple("U10.IN", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.decouple("U10.OUT", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.auto_ref("D");
    c.part("D10", "Device:LED", "red", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C2286"}});
    c.auto_ref("R");
    c.part("R20", "Device:R", "1k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C21190"}});
    c.net("+5V_LCD", {"D10.2"}, std::nullopt);
    c.net("BU_PG_LCD_5V", {"D10.1", "R20.1"}, std::nullopt);
    c.net("GND", {"R20.2"}, std::nullopt);
    c.auto_ref("R");
    c.part("R21", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25804"}});
    c.net("+3V3_SD", {"R21.1"}, std::nullopt);
    c.net("GND", {"R21.2"}, std::nullopt);
    c.testpoint("+3V3_HDMI_TX", std::nullopt);
    c.testpoint("+3V3_HDMI_RX", std::nullopt);
    c.testpoint("+3V3_LCD", std::nullopt);
    c.testpoint("+3V3_CAM", std::nullopt);
    c.testpoint("+3V3_SD", std::nullopt);
    c.testpoint("+5V_USB", std::nullopt);
    c.testpoint("+3V3_PMOD", std::nullopt);
    c.testpoint("+3V3_USER_LED", std::nullopt);
    c.testpoint("+5V_HDMI_TX", std::nullopt);
    c.testpoint("+5V_LCD", std::nullopt);
    c.draws("+3V3_HDMI_TX", 0.004, "status LED (330R) on the gated output");
    c.draws("+3V3_HDMI_RX", 0.004, "status LED (330R) on the gated output");
    c.draws("+3V3_LCD", 0.004, "status LED (330R) on the gated output");
    c.draws("+3V3_CAM", 0.004, "status LED (330R) on the gated output");
    c.draws("+3V3_SD", 0.004, "status LED (330R) on the gated output");
    c.draws("+5V_USB", 0.003, "status LED (1k) on the gated output");
    c.draws("+3V3_PMOD", 0.004, "status LED (330R) on the gated output");
    c.draws("+3V3_USER_LED", 0.004, "status LED (330R) on the gated output");
    c.draws("+5V_HDMI_TX", 0.003, "status LED (1k) on the gated output");
    c.draws("+5V_LCD", 0.003, "status LED (1k) on the gated output");
    c.field("C1", "LCSC", "C14663");
    c.field("C2", "LCSC", "C14663");
    c.field("C3", "LCSC", "C14663");
    c.field("C4", "LCSC", "C14663");
    c.field("C5", "LCSC", "C14663");
    c.field("C6", "LCSC", "C14663");
    c.field("C7", "LCSC", "C14663");
    c.field("C8", "LCSC", "C14663");
    c.field("C9", "LCSC", "C14663");
    c.field("C10", "LCSC", "C14663");
    c.field("C11", "LCSC", "C14663");
    c.field("C12", "LCSC", "C14663");
    c.field("C13", "LCSC", "C14663");
    c.field("C14", "LCSC", "C14663");
    c.field("C15", "LCSC", "C14663");
    c.field("C16", "LCSC", "C14663");
    c.field("C17", "LCSC", "C14663");
    c.field("C18", "LCSC", "C14663");
    c.field("C19", "LCSC", "C14663");
    c.field("C20", "LCSC", "C14663");
    return meta.finish(c);
}
} // namespace schgen::project_builders
