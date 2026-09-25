#include "schgen/subsystem_authoring.hpp"

namespace schgen::subsystem_builders {
// Migrated construction operations from subsystems/power/power.py.
CircuitSheetIr power(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("power", "Power: +VIN->+5V->+3V3 bucks + +1V8 LDO, PG LEDs", context);
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        c.use_part("LM61460AANRJRR", p);
    }
    c.net("+VIN", {"U1.8", "U1.12"}, std::nullopt);
    c.net("GND", {"U1.9", "U1.11", "U1.3"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("EN_VOUT_5V");
        c.port("EN_VOUT_5V", {"U1.7"}, t, false);
    }
    c.part("C1", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+VIN", {"C1.1"}, std::nullopt);
    c.net("GND", {"C1.2"}, std::nullopt);
    c.part("C25", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+VIN", {"C25.1"}, std::nullopt);
    c.net("GND", {"C25.2"}, std::nullopt);
    c.part("C2", "Device:C", "10u", "Capacitor_SMD:C_1206_3216Metric", {{"LCSC", "C13585"}});
    c.net("+VIN", {"C2.1"}, std::nullopt);
    c.net("GND", {"C2.2"}, std::nullopt);
    c.part("C3", "Device:C", "10u", "Capacitor_SMD:C_1206_3216Metric", {{"LCSC", "C13585"}});
    c.net("+VIN", {"C3.1"}, std::nullopt);
    c.net("GND", {"C3.2"}, std::nullopt);
    c.part("C24", "Device:C", "1u", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C15849"}});
    c.net("U1_VCC", {"U1.2", "C24.1"}, std::nullopt);
    c.net("GND", {"C24.2"}, std::nullopt);
    c.part("R11", "Device:R", "10R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22859"}});
    c.net("+VOUT_5V_REG", {"R11.1"}, std::nullopt);
    c.part("C28", "Device:C", "1u", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C15849"}});
    c.net("BIAS_5V0", {"U1.1", "R11.2", "C28.1"}, std::nullopt);
    c.net("GND", {"C28.2"}, std::nullopt);
    c.part("R10", "Device:R", "22k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C31850"}});
    c.net("RT_5V0", {"U1.6", "R10.1"}, std::nullopt);
    c.net("GND", {"R10.2"}, std::nullopt);
    c.part("C4", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("BOOT_5V0", {"U1.14", "U1.13", "C4.1"}, std::nullopt);
    c.part("L1", "Device:L", "10uH", "SWPA8040S100MT:SWPA8040S100MT", {{"LCSC", "C37429"}});
    c.net("SW_5V0", {"U1.10", "C4.2", "L1.1"}, std::nullopt);
    c.net("+VOUT_5V_REG", {"L1.2"}, std::nullopt);
    c.part("C5", "Device:C", "22u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C45783"}});
    c.net("+VOUT_5V_REG", {"C5.1"}, std::nullopt);
    c.net("GND", {"C5.2"}, std::nullopt);
    c.part("C6", "Device:C", "22u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C45783"}});
    c.net("+VOUT_5V_REG", {"C6.1"}, std::nullopt);
    c.net("GND", {"C6.2"}, std::nullopt);
    c.part("C26", "Device:C", "22u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C45783"}});
    c.net("+VOUT_5V_REG", {"C26.1"}, std::nullopt);
    c.net("GND", {"C26.2"}, std::nullopt);
    c.part("R1", "Device:R", "40.2k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C12447"}});
    c.part("R2", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25804"}});
    c.net("+VOUT_5V_REG", {"R1.1"}, std::nullopt);
    c.net("FB_5V0", {"U1.4", "R1.2", "R2.1"}, std::nullopt);
    c.net("GND", {"R2.2"}, std::nullopt);
    c.part("C27", "Device:C", "22p", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C1653"}});
    c.part("R12", "Device:R", "1k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C21190"}});
    c.net("+VOUT_5V_REG", {"C27.1"}, std::nullopt);
    c.net("CFF_5V0", {"C27.2", "R12.1"}, std::nullopt);
    c.net("FB_5V0", {"R12.2"}, std::nullopt);
    c.part("D1", "Device:LED", "red", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C2286"}});
    c.part("R3", "Device:R", "1k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C21190"}});
    c.net("+VOUT_5V_REG", {"D1.2"}, std::nullopt);
    c.net("PG_5V0", {"D1.1", "R3.1"}, std::nullopt);
    c.net("GND", {"R3.2"}, std::nullopt);
    c.nc({"U1.5"});
    {
        AuthoringPartSelection p;
        p.ref = "U2";
        c.use_part("LM61460AANRJRR", p);
    }
    c.net("+VOUT_5V", {"U2.8", "U2.12"}, std::nullopt);
    c.net("GND", {"U2.9", "U2.11", "U2.3"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("EN_VOUT_3V3");
        c.port("EN_VOUT_3V3", {"U2.7"}, t, false);
    }
    c.part("C7", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+VOUT_5V", {"C7.1"}, std::nullopt);
    c.net("GND", {"C7.2"}, std::nullopt);
    c.part("C29", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+VOUT_5V", {"C29.1"}, std::nullopt);
    c.net("GND", {"C29.2"}, std::nullopt);
    c.part("C8", "Device:C", "22u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C45783"}});
    c.net("+VOUT_5V", {"C8.1"}, std::nullopt);
    c.net("GND", {"C8.2"}, std::nullopt);
    c.part("C30", "Device:C", "22u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C45783"}});
    c.net("+VOUT_5V", {"C30.1"}, std::nullopt);
    c.net("GND", {"C30.2"}, std::nullopt);
    c.part("C31", "Device:C", "1u", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C15849"}});
    c.net("U2_VCC", {"U2.2", "C31.1"}, std::nullopt);
    c.net("GND", {"C31.2"}, std::nullopt);
    c.part("R13", "Device:R", "10R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22859"}});
    c.net("+VOUT_3V3_REG", {"R13.1"}, std::nullopt);
    c.part("C32", "Device:C", "1u", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C15849"}});
    c.net("BIAS_3V3", {"U2.1", "R13.2", "C32.1"}, std::nullopt);
    c.net("GND", {"C32.2"}, std::nullopt);
    c.part("R14", "Device:R", "22k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C31850"}});
    c.net("RT_3V3", {"U2.6", "R14.1"}, std::nullopt);
    c.net("GND", {"R14.2"}, std::nullopt);
    c.part("C9", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("BOOT_3V3", {"U2.14", "U2.13", "C9.1"}, std::nullopt);
    c.part("L2", "Device:L", "10uH", "SWPA8040S100MT:SWPA8040S100MT", {{"LCSC", "C37429"}});
    c.net("SW_3V3", {"U2.10", "C9.2", "L2.1"}, std::nullopt);
    c.net("+VOUT_3V3_REG", {"L2.2"}, std::nullopt);
    c.part("C10", "Device:C", "22u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C45783"}});
    c.net("+VOUT_3V3_REG", {"C10.1"}, std::nullopt);
    c.net("GND", {"C10.2"}, std::nullopt);
    c.part("C11", "Device:C", "22u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C45783"}});
    c.net("+VOUT_3V3_REG", {"C11.1"}, std::nullopt);
    c.net("GND", {"C11.2"}, std::nullopt);
    c.part("R4", "Device:R", "23.2k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23346"}});
    c.part("R5", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25804"}});
    c.net("+VOUT_3V3_REG", {"R4.1"}, std::nullopt);
    c.net("FB_3V3", {"U2.4", "R4.2", "R5.1"}, std::nullopt);
    c.net("GND", {"R5.2"}, std::nullopt);
    c.part("C23", "Device:C", "22p", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C1653"}});
    c.part("R15", "Device:R", "1k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C21190"}});
    c.net("+VOUT_3V3_REG", {"C23.1"}, std::nullopt);
    c.net("CFF_3V3", {"C23.2", "R15.1"}, std::nullopt);
    c.net("FB_3V3", {"R15.2"}, std::nullopt);
    c.part("D2", "Device:LED", "red", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C2286"}});
    c.part("R6", "Device:R", "330R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23138"}});
    c.net("+VOUT_3V3_REG", {"D2.2"}, std::nullopt);
    c.net("PG_3V3", {"D2.1", "R6.1"}, std::nullopt);
    c.net("GND", {"R6.2"}, std::nullopt);
    c.nc({"U2.5"});
    {
        AuthoringPartSelection p;
        p.ref = "U3";
        p.value = "AP2112K-1.8";
        p.lib_id = "Regulator_Linear:AP2204K-1.5";
        p.footprint = "Package_TO_SOT_SMD:SOT-23-5";
        c.use_part("AP2112K-1.8TRG1", p);
    }
    c.net("+VOUT_3V3", {"U3.1"}, std::nullopt);
    c.net("GND", {"U3.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("EN_VOUT_1V8");
        c.port("EN_VOUT_1V8", {"U3.3"}, t, false);
    }
    c.nc({"U3.4"});
    c.net("+VOUT_1V8_REG", {"U3.5"}, std::nullopt);
    c.part("C12", "Device:C", "1u", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C15849"}});
    c.net("+VOUT_3V3", {"C12.1"}, std::nullopt);
    c.net("GND", {"C12.2"}, std::nullopt);
    c.part("C13", "Device:C", "1u", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C15849"}});
    c.net("+VOUT_1V8_REG", {"C13.1"}, std::nullopt);
    c.net("GND", {"C13.2"}, std::nullopt);
    c.part("R7", "Device:R", "1k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C21190"}});
    c.part("R8", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    {
        AuthoringPartSelection p;
        p.ref = "Q1";
        p.lib_id = "Transistor_FET:Q_NMOS_GSD";
        p.footprint = "Package_TO_SOT_SMD:SOT-23";
        c.use_part("AO3400A", p);
    }
    c.net("+VOUT_1V8", {"R7.1"}, std::nullopt);
    c.net("PG_1V8_G", {"R7.2", "R8.1", "Q1.1"}, std::nullopt);
    c.net("GND", {"R8.2", "Q1.2"}, std::nullopt);
    c.part("R9", "Device:R", "330R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23138"}});
    c.part("D3", "Device:LED", "red", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C2286"}});
    c.net("PG_1V8_D", {"Q1.3", "R9.2"}, std::nullopt);
    c.net("PG_1V8_K", {"R9.1", "D3.1"}, std::nullopt);
    c.net("+VOUT_3V3", {"D3.2"}, std::nullopt);
    c.testpoint("+VOUT_5V", std::nullopt);
    c.testpoint("+VOUT_3V3", std::nullopt);
    c.testpoint("+VOUT_1V8", std::nullopt);
    c.testpoint("GND", std::nullopt);
    c.draws("+VOUT_5V", 0.004, meta.note("draws_5v", "PG LED + FB divider"));
    c.draws("+VOUT_3V3", 0.009, meta.note("draws_3v3", "PG LED + downstream PG-sense LED chain + FB divider"));
    c.draws("+VOUT_1V8", 0.001, meta.note("draws_1v8", "PG FET gate divider"));
    return meta.finish(c);
}
} // namespace schgen::subsystem_builders
