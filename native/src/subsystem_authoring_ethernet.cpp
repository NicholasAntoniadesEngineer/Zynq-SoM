#include "schgen/subsystem_authoring.hpp"

namespace schgen::subsystem_builders {
// Migrated construction operations from subsystems/ethernet/ethernet.py.
CircuitSheetIr ethernet(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("ethernet", "Ethernet: HX5008NL magnetics + Bob-Smith", context);
    {
        AuthoringPartSelection p;
        p.ref = "T1";
        c.use_part("HX5008NLT", p);
    }
    {
        AuthoringPort t;
        c.port("MDI0_P", {"T1.2"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("MDI0_N", {"T1.3"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("MX0_P", {"T1.23"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("MX0_N", {"T1.22"}, t, false);
    }
    c.nc({"T1.1"});
    {
        AuthoringPort t;
        c.port("MDI1_P", {"T1.5"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("MDI1_N", {"T1.6"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("MX1_P", {"T1.20"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("MX1_N", {"T1.19"}, t, false);
    }
    c.nc({"T1.4"});
    {
        AuthoringPort t;
        c.port("MDI2_P", {"T1.8"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("MDI2_N", {"T1.9"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("MX2_P", {"T1.17"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("MX2_N", {"T1.16"}, t, false);
    }
    c.nc({"T1.7"});
    {
        AuthoringPort t;
        c.port("MDI3_P", {"T1.11"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("MDI3_N", {"T1.12"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("MX3_P", {"T1.14"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("MX3_N", {"T1.13"}, t, false);
    }
    c.nc({"T1.10"});
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "MDI0_N";
        t.impedance = 100;
        c.port_type("MDI0_P", t);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "MX0_N";
        t.impedance = 100;
        t.expect = meta.expect_kw("MX0_P");
        c.port_type("MX0_P", t);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "MDI1_N";
        t.impedance = 100;
        c.port_type("MDI1_P", t);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "MX1_N";
        t.impedance = 100;
        t.expect = meta.expect_kw("MX1_P");
        c.port_type("MX1_P", t);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "MDI2_N";
        t.impedance = 100;
        c.port_type("MDI2_P", t);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "MX2_N";
        t.impedance = 100;
        t.expect = meta.expect_kw("MX2_P");
        c.port_type("MX2_P", t);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "MDI3_N";
        t.impedance = 100;
        c.port_type("MDI3_P", t);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "MX3_N";
        t.impedance = 100;
        t.expect = meta.expect_kw("MX3_P");
        c.port_type("MX3_P", t);
    }
    c.part("R1", "Device:R", "75R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C4275"}});
    c.part("C1", "Device:C", "1n", "Capacitor_SMD:C_1206_3225Metric", {{"LCSC", "C9196"}});
    c.net("MCT1", {"T1.24", "R1.1", "C1.1"}, std::nullopt);
    c.net("BS_COMMON", {"R1.2", "C1.2"}, std::nullopt);
    c.part("R2", "Device:R", "75R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C4275"}});
    c.part("C2", "Device:C", "1n", "Capacitor_SMD:C_1206_3225Metric", {{"LCSC", "C9196"}});
    c.net("MCT2", {"T1.21", "R2.1", "C2.1"}, std::nullopt);
    c.net("BS_COMMON", {"R2.2", "C2.2"}, std::nullopt);
    c.part("R3", "Device:R", "75R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C4275"}});
    c.part("C3", "Device:C", "1n", "Capacitor_SMD:C_1206_3225Metric", {{"LCSC", "C9196"}});
    c.net("MCT3", {"T1.18", "R3.1", "C3.1"}, std::nullopt);
    c.net("BS_COMMON", {"R3.2", "C3.2"}, std::nullopt);
    c.part("R4", "Device:R", "75R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C4275"}});
    c.part("C4", "Device:C", "1n", "Capacitor_SMD:C_1206_3225Metric", {{"LCSC", "C9196"}});
    c.net("MCT4", {"T1.15", "R4.1", "C4.1"}, std::nullopt);
    c.net("BS_COMMON", {"R4.2", "C4.2"}, std::nullopt);
    c.part("C5", "Device:C", "1n", "Capacitor_SMD:C_1206_3225Metric", {{"LCSC", "C9196"}});
    c.net("BS_COMMON", {"C5.1"}, std::nullopt);
    c.net("CHASSIS_GND", {"C5.2"}, std::nullopt);
    c.field("T1", "ALT_LCSC", "C47575004");
    return meta.finish(c);
}
} // namespace schgen::subsystem_builders
