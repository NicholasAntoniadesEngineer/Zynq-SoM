#include "schgen/subsystem_authoring.hpp"

namespace schgen::project_builders {
// Migrated construction operations from carrier/subsystems/bringup_en/bringup_en.py.
CircuitSheetIr carrier_bringup_en(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("bringup_en", "Bring-up EN cells: 3x SN74LVC1G08 rail DIP-AND-override", context);
    c.part("U1", "74xGxx:74LVC1G08", "SN74LVC1G08", "Package_TO_SOT_SMD:SOT-23-5", {{"LCSC", "C7666"}});
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_DIP_5V0", {"U1.1"}, t, true);
    }
    c.auto_ref("R");
    c.part("R1", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("BU_DIP_5V0", {"R1.1"}, std::nullopt);
    c.net("GND", {"R1.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "som_j3_connector (wave 3 STM32 GPIO function map)";
        c.port("STM32_RAIL_EN_5V0", {"U1.2"}, t, true);
    }
    c.pullup("U1.2", "100k", "+3V3_SC", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    {
        AuthoringPort t;
        t.expect = "power (regulator EN pins, dossier section 3.1)";
        c.port("EN_5V0", {"U1.4"}, t, true);
    }
    c.net("+3V3_SC", {"U1.5"}, std::nullopt);
    c.net("GND", {"U1.3"}, std::nullopt);
    c.decouple("U1.5", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.part("U2", "74xGxx:74LVC1G08", "SN74LVC1G08", "Package_TO_SOT_SMD:SOT-23-5", {{"LCSC", "C7666"}});
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_DIP_3V3", {"U2.1"}, t, true);
    }
    c.auto_ref("R");
    c.part("R3", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("BU_DIP_3V3", {"R3.1"}, std::nullopt);
    c.net("GND", {"R3.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "som_j3_connector (wave 3 STM32 GPIO function map)";
        c.port("STM32_RAIL_EN_3V3", {"U2.2"}, t, true);
    }
    c.pullup("U2.2", "100k", "+3V3_SC", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    {
        AuthoringPort t;
        t.expect = "power (regulator EN pins, dossier section 3.1)";
        c.port("EN_3V3", {"U2.4"}, t, true);
    }
    c.net("+3V3_SC", {"U2.5"}, std::nullopt);
    c.net("GND", {"U2.3"}, std::nullopt);
    c.decouple("U2.5", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.part("U3", "74xGxx:74LVC1G08", "SN74LVC1G08", "Package_TO_SOT_SMD:SOT-23-5", {{"LCSC", "C7666"}});
    {
        AuthoringPort t;
        t.expect = "bringup_rails (DIP / TCA9535 control surfaces)";
        c.port("BU_DIP_1V8", {"U3.1"}, t, true);
    }
    c.auto_ref("R");
    c.part("R5", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("BU_DIP_1V8", {"R5.1"}, std::nullopt);
    c.net("GND", {"R5.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "som_j3_connector (wave 3 STM32 GPIO function map)";
        c.port("STM32_RAIL_EN_1V8", {"U3.2"}, t, true);
    }
    c.pullup("U3.2", "100k", "+3V3_SC", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    {
        AuthoringPort t;
        t.expect = "power (regulator EN pins, dossier section 3.1)";
        c.port("EN_1V8", {"U3.4"}, t, true);
    }
    c.net("+3V3_SC", {"U3.5"}, std::nullopt);
    c.net("GND", {"U3.3"}, std::nullopt);
    c.decouple("U3.5", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.testpoint("EN_5V0", std::nullopt);
    c.testpoint("EN_3V3", std::nullopt);
    c.testpoint("EN_1V8", std::nullopt);
    c.draws("+3V3_SC", 0.002, "3x SN74LVC1G08 + 100k pull networks");
    c.field("R2", "LCSC", "C25803");
    c.field("C1", "LCSC", "C14663");
    c.field("R4", "LCSC", "C25803");
    c.field("C2", "LCSC", "C14663");
    c.field("R6", "LCSC", "C25803");
    c.field("C3", "LCSC", "C14663");
    return meta.finish(c);
}
} // namespace schgen::project_builders
