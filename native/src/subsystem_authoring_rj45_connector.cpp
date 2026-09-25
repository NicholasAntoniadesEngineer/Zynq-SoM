#include "schgen/subsystem_authoring.hpp"

namespace schgen::subsystem_builders {
// Migrated construction operations from subsystems/rj45_connector/rj45_connector.py.
CircuitSheetIr rj45_connector(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("rj45_connector", "RJ45 8P8C jack (plain, ext. magnetics)", context);
    {
        AuthoringPartSelection p;
        p.ref = "J1";
        c.use_part("KH-5224-8P8C-D", p);
    }
    {
        AuthoringPort t;
        c.port("RJ45_MDI0_P", {"J1.1"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("RJ45_MDI0_N", {"J1.2"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("RJ45_MDI1_P", {"J1.3"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("RJ45_MDI1_N", {"J1.6"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("RJ45_MDI2_P", {"J1.4"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("RJ45_MDI2_N", {"J1.5"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("RJ45_MDI3_P", {"J1.7"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("RJ45_MDI3_N", {"J1.8"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "RJ45_MDI0_N";
        t.impedance = 100;
        t.expect = meta.expect_kw("RJ45_MDI0_P");
        c.port_type("RJ45_MDI0_P", t);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "RJ45_MDI1_N";
        t.impedance = 100;
        t.expect = meta.expect_kw("RJ45_MDI1_P");
        c.port_type("RJ45_MDI1_P", t);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "RJ45_MDI2_N";
        t.impedance = 100;
        t.expect = meta.expect_kw("RJ45_MDI2_P");
        c.port_type("RJ45_MDI2_P", t);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "RJ45_MDI3_N";
        t.impedance = 100;
        t.expect = meta.expect_kw("RJ45_MDI3_P");
        c.port_type("RJ45_MDI3_P", t);
    }
    c.part("R1", "Device:R", "330R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23138"}});
    c.net("+VLED", {"R1.1"}, std::nullopt);
    c.net("RJ45_LED_L", {"R1.2", "J1.9"}, std::nullopt);
    c.net("GND", {"J1.10"}, std::nullopt);
    c.part("R2", "Device:R", "330R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23138"}});
    c.net("+VLED", {"R2.1"}, std::nullopt);
    c.net("RJ45_LED_R", {"R2.2", "J1.11"}, std::nullopt);
    c.net("GND", {"J1.12"}, std::nullopt);
    c.net("CHASSIS_GND", {"J1.13"}, std::nullopt);
    c.draws("+VLED", 0.008, meta.note("draws", "RJ45 housing LEDs (2x 330R port-present indicator)"));
    return meta.finish(c);
}
} // namespace schgen::subsystem_builders
