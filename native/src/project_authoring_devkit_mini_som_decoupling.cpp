#include "schgen/subsystem_authoring.hpp"

namespace schgen::project_builders {
// Migrated construction operations from devkit_mini/subsystems/som_decoupling/som_decoupling.py.
CircuitSheetIr devkit_mini_som_decoupling(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("som_decoupling", "SoM power-entry decoupling under the DF40 mezzanine", context);
    c.part("C1", "Device:C", "22u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C45783"}});
    c.net("+5V_SOM", {"C1.1"}, std::nullopt);
    c.net("GND", {"C1.2"}, std::nullopt);
    c.part("C2", "Device:C", "22u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C45783"}});
    c.net("+5V_SOM", {"C2.1"}, std::nullopt);
    c.net("GND", {"C2.2"}, std::nullopt);
    c.part("C3", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+5V_SOM", {"C3.1"}, std::nullopt);
    c.net("GND", {"C3.2"}, std::nullopt);
    c.part("C4", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+5V_SOM", {"C4.1"}, std::nullopt);
    c.net("GND", {"C4.2"}, std::nullopt);
    c.part("C5", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+5V_SOM", {"C5.1"}, std::nullopt);
    c.net("GND", {"C5.2"}, std::nullopt);
    c.part("C6", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+5V_SOM", {"C6.1"}, std::nullopt);
    c.net("GND", {"C6.2"}, std::nullopt);
    c.part("C7", "Device:C", "22u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C45783"}});
    c.net("+3V3", {"C7.1"}, std::nullopt);
    c.net("GND", {"C7.2"}, std::nullopt);
    c.part("C8", "Device:C", "22u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C45783"}});
    c.net("+3V3", {"C8.1"}, std::nullopt);
    c.net("GND", {"C8.2"}, std::nullopt);
    c.part("C9", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+3V3", {"C9.1"}, std::nullopt);
    c.net("GND", {"C9.2"}, std::nullopt);
    c.part("C10", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+3V3", {"C10.1"}, std::nullopt);
    c.net("GND", {"C10.2"}, std::nullopt);
    c.part("C11", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+3V3", {"C11.1"}, std::nullopt);
    c.net("GND", {"C11.2"}, std::nullopt);
    c.part("C12", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+3V3", {"C12.1"}, std::nullopt);
    c.net("GND", {"C12.2"}, std::nullopt);
    c.part("C13", "Device:C", "22u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C45783"}});
    c.net("+3V3_SC", {"C13.1"}, std::nullopt);
    c.net("GND", {"C13.2"}, std::nullopt);
    c.part("C14", "Device:C", "22u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C45783"}});
    c.net("+3V3_SC", {"C14.1"}, std::nullopt);
    c.net("GND", {"C14.2"}, std::nullopt);
    c.part("C15", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+3V3_SC", {"C15.1"}, std::nullopt);
    c.net("GND", {"C15.2"}, std::nullopt);
    c.part("C16", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+3V3_SC", {"C16.1"}, std::nullopt);
    c.net("GND", {"C16.2"}, std::nullopt);
    c.part("C17", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+3V3_SC", {"C17.1"}, std::nullopt);
    c.net("GND", {"C17.2"}, std::nullopt);
    c.part("C18", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+3V3_SC", {"C18.1"}, std::nullopt);
    c.net("GND", {"C18.2"}, std::nullopt);
    return meta.finish(c);
}
} // namespace schgen::project_builders
