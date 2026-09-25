#include "schgen/subsystem_authoring.hpp"

namespace schgen::project_builders {
// Migrated construction operations from devkit_mini/subsystems/power_som/power_som.py.
CircuitSheetIr devkit_mini_power_som(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("power_som", "Power: +VIN -> +5V_SOM always-on buck", context);
    {
        AuthoringPartSelection p;
        p.ref = "U4";
        c.use_part("LM61460AANRJRR", p);
    }
    c.net("+VIN_SYS", {"U4.8", "U4.12"}, std::nullopt);
    c.net("GND", {"U4.9", "U4.11", "U4.3"}, std::nullopt);
    c.part("R12", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25804"}});
    c.part("D5", "Device:D_Zener", "MMSZ5231B", "Diode_SMD:D_SOD-123", {{"LCSC", "C85181"}});
    c.part("C20", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+VIN_SYS", {"R12.1"}, std::nullopt);
    c.net("EN_5V_SOM", {"U4.7", "R12.2", "D5.1", "C20.1"}, std::nullopt);
    c.net("GND", {"D5.2", "C20.2"}, std::nullopt);
    c.part("C14", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+VIN_SYS", {"C14.1"}, std::nullopt);
    c.net("GND", {"C14.2"}, std::nullopt);
    c.part("C25", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+VIN_SYS", {"C25.1"}, std::nullopt);
    c.net("GND", {"C25.2"}, std::nullopt);
    c.part("C15", "Device:C", "10u", "Capacitor_SMD:C_1206_3216Metric", {{"LCSC", "C13585"}});
    c.net("+VIN_SYS", {"C15.1"}, std::nullopt);
    c.net("GND", {"C15.2"}, std::nullopt);
    c.part("C16", "Device:C", "10u", "Capacitor_SMD:C_1206_3216Metric", {{"LCSC", "C13585"}});
    c.net("+VIN_SYS", {"C16.1"}, std::nullopt);
    c.net("GND", {"C16.2"}, std::nullopt);
    c.part("C22", "Device:C", "1u", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C15849"}});
    c.net("U4_VCC", {"U4.2", "C22.1"}, std::nullopt);
    c.net("GND", {"C22.2"}, std::nullopt);
    c.part("R17", "Device:R", "10R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22859"}});
    c.net("+5V_SOM", {"R17.1"}, std::nullopt);
    c.part("C23", "Device:C", "1u", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C15849"}});
    c.net("BIAS_5V_SOM", {"U4.1", "R17.2", "C23.1"}, std::nullopt);
    c.net("GND", {"C23.2"}, std::nullopt);
    c.part("R18", "Device:R", "22k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C31850"}});
    c.net("RT_5V_SOM", {"U4.6", "R18.1"}, std::nullopt);
    c.net("GND", {"R18.2"}, std::nullopt);
    c.part("C17", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("BOOT_5V_SOM", {"U4.14", "U4.13", "C17.1"}, std::nullopt);
    c.part("L3", "Device:L", "10uH", "SWPA8040S100MT:SWPA8040S100MT", {{"LCSC", "C37429"}});
    c.net("SW_5V_SOM", {"U4.10", "C17.2", "L3.1"}, std::nullopt);
    c.net("+5V_SOM", {"L3.2"}, std::nullopt);
    c.part("C18", "Device:C", "22u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C45783"}});
    c.net("+5V_SOM", {"C18.1"}, std::nullopt);
    c.net("GND", {"C18.2"}, std::nullopt);
    c.part("C19", "Device:C", "22u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C45783"}});
    c.net("+5V_SOM", {"C19.1"}, std::nullopt);
    c.net("GND", {"C19.2"}, std::nullopt);
    c.part("R14", "Device:R", "47.5k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23061"}});
    c.part("R15", "Device:R", "13k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22797"}});
    c.net("+5V_SOM", {"R14.1"}, std::nullopt);
    c.net("FB_5V_SOM", {"U4.4", "R14.2", "R15.1"}, std::nullopt);
    c.net("GND", {"R15.2"}, std::nullopt);
    c.part("C21", "Device:C", "22p", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C1653"}});
    c.part("R19", "Device:R", "1k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C21190"}});
    c.net("+5V_SOM", {"C21.1"}, std::nullopt);
    c.net("CFF_5V_SOM", {"C21.2", "R19.1"}, std::nullopt);
    c.net("FB_5V_SOM", {"R19.2"}, std::nullopt);
    c.part("D4", "Device:LED", "red", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C2286"}});
    c.part("R16", "Device:R", "1k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C21190"}});
    c.net("+5V_SOM", {"D4.2"}, std::nullopt);
    c.net("PG_5V_SOM", {"D4.1", "R16.1"}, std::nullopt);
    c.net("GND", {"R16.2"}, std::nullopt);
    c.nc({"U4.5"});
    c.testpoint("+5V_SOM", std::nullopt);
    c.draws("+5V_SOM", 0.004, "PG LED (KT-0603R + 1k, ~3 mA) + FB divider 60 uA (SoM module load declared on som_j1)");
    return meta.finish(c);
}
} // namespace schgen::project_builders
