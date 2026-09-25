#include "schgen/subsystem_authoring.hpp"

namespace schgen::project_builders {
// Migrated construction operations from carrier/subsystems/user_io/user_io.py.
CircuitSheetIr carrier_user_io(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("user_io", "User IO: 4 LEDs (gated rail) + 4 buttons, bank 13", context);
    c.part("D1", "Device:LED", "red", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C2286"}});
    c.part("R1", "Device:R", "1k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C21190"}});
    c.net("USER_LED1_K", {"D1.1", "R1.1"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "som_j2_connector";
        c.port("IO_25_13", {"R1.2"}, t, true);
    }
    c.part("D2", "Device:LED", "green", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C12624"}});
    c.part("R2", "Device:R", "200R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C8218"}});
    c.net("USER_LED2_K", {"D2.1", "R2.1"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "som_j2_connector";
        c.port("IO_L6_P_13", {"R2.2"}, t, true);
    }
    c.part("D3", "Device:LED", "blue", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C2288"}});
    c.part("R3", "Device:R", "200R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C8218"}});
    c.net("USER_LED3_K", {"D3.1", "R3.1"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "som_j2_connector";
        c.port("IO_L24_P_13", {"R3.2"}, t, true);
    }
    c.part("D4", "Device:LED", "white", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C2290"}});
    c.part("R4", "Device:R", "200R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C8218"}});
    c.net("USER_LED4_K", {"D4.1", "R4.1"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "som_j2_connector";
        c.port("IO_L24_N_13", {"R4.2"}, t, true);
    }
    c.part("C1", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+3V3_USER_LED", {"D1.2", "D2.2", "D3.2", "D4.2", "C1.1"}, std::nullopt);
    c.net("GND", {"C1.2"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "SW1";
        p.value = "USER";
        c.use_part("TS-1187A-B-A-B", p);
    }
    c.part("R5", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25804"}});
    {
        AuthoringPort t;
        t.expect = "som_j2_connector";
        c.port("IO_L15_P_13", {"SW1.1", "SW1.2", "R5.2"}, t, true);
    }
    c.net("+3V3", {"R5.1"}, std::nullopt);
    c.net("GND", {"SW1.3", "SW1.4"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "SW2";
        p.value = "USER";
        c.use_part("TS-1187A-B-A-B", p);
    }
    c.part("R6", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25804"}});
    {
        AuthoringPort t;
        t.expect = "som_j2_connector";
        c.port("IO_L19_P_13", {"SW2.1", "SW2.2", "R6.2"}, t, true);
    }
    c.net("+3V3", {"R6.1"}, std::nullopt);
    c.net("GND", {"SW2.3", "SW2.4"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "SW3";
        p.value = "USER";
        c.use_part("TS-1187A-B-A-B", p);
    }
    c.part("R7", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25804"}});
    {
        AuthoringPort t;
        t.expect = "som_j2_connector";
        c.port("IO_L21_P_13", {"SW3.1", "SW3.2", "R7.2"}, t, true);
    }
    c.net("+3V3", {"R7.1"}, std::nullopt);
    c.net("GND", {"SW3.3", "SW3.4"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "SW4";
        p.value = "USER";
        c.use_part("TS-1187A-B-A-B", p);
    }
    c.part("R8", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25804"}});
    {
        AuthoringPort t;
        t.expect = "som_j2_connector";
        c.port("IO_L22_P_13", {"SW4.1", "SW4.2", "R8.2"}, t, true);
    }
    c.net("+3V3", {"R8.1"}, std::nullopt);
    c.net("GND", {"SW4.3", "SW4.4"}, std::nullopt);
    c.draws("+3V3_USER_LED", 0.012, "red ~1.3 mA (1k) + green/blue/white up to ~3.5 mA each (200R)");
    c.draws("+3V3", 0.002, "4x button 10k pull-ups when pressed");
    return meta.finish(c);
}
} // namespace schgen::project_builders
