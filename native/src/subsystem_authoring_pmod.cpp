#include "schgen/subsystem_authoring.hpp"

namespace schgen::subsystem_builders {
// Migrated construction operations from subsystems/pmod/pmod.py.
CircuitSheetIr pmod(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("pmod", "2x Pmod host ports (bank 13, 200R series, gated 3V3)", context);
    {
        AuthoringPartSelection p;
        p.ref = "J1";
        c.use_part("DS1024-2x6R2", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        p.value = "TPD4E1U06";
        c.use_part("TPD4E1U06DBVR", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U2";
        p.value = "TPD4E1U06";
        c.use_part("TPD4E1U06DBVR", p);
    }
    c.part("R1", "Device:R", "200R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C8218"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD0_SIG1");
        c.port("PMOD0_SIG1", {"R1.1", "U1.1"}, t, false);
    }
    c.net("PMOD0_IO1", {"R1.2", "J1.1"}, std::nullopt);
    c.part("R2", "Device:R", "200R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C8218"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD0_SIG2");
        c.port("PMOD0_SIG2", {"R2.1", "U1.3"}, t, false);
    }
    c.net("PMOD0_IO2", {"R2.2", "J1.3"}, std::nullopt);
    c.part("R3", "Device:R", "200R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C8218"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD0_SIG3");
        c.port("PMOD0_SIG3", {"R3.1", "U1.6"}, t, false);
    }
    c.net("PMOD0_IO3", {"R3.2", "J1.5"}, std::nullopt);
    c.part("R4", "Device:R", "200R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C8218"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD0_SIG4");
        c.port("PMOD0_SIG4", {"R4.1", "U1.4"}, t, false);
    }
    c.net("PMOD0_IO4", {"R4.2", "J1.7"}, std::nullopt);
    c.part("R5", "Device:R", "200R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C8218"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD0_SIG5");
        c.port("PMOD0_SIG5", {"R5.1", "U2.1"}, t, false);
    }
    c.net("PMOD0_IO5", {"R5.2", "J1.2"}, std::nullopt);
    c.part("R6", "Device:R", "200R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C8218"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD0_SIG6");
        c.port("PMOD0_SIG6", {"R6.1", "U2.3"}, t, false);
    }
    c.net("PMOD0_IO6", {"R6.2", "J1.4"}, std::nullopt);
    c.part("R7", "Device:R", "200R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C8218"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD0_SIG7");
        c.port("PMOD0_SIG7", {"R7.1", "U2.6"}, t, false);
    }
    c.net("PMOD0_IO7", {"R7.2", "J1.6"}, std::nullopt);
    c.part("R8", "Device:R", "200R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C8218"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD0_SIG8");
        c.port("PMOD0_SIG8", {"R8.1", "U2.4"}, t, false);
    }
    c.net("PMOD0_IO8", {"R8.2", "J1.8"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "J2";
        c.use_part("DS1024-2x6R2", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U3";
        p.value = "TPD4E1U06";
        c.use_part("TPD4E1U06DBVR", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U4";
        p.value = "TPD4E1U06";
        c.use_part("TPD4E1U06DBVR", p);
    }
    c.part("R9", "Device:R", "200R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C8218"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD1_SIG1");
        c.port("PMOD1_SIG1", {"R9.1", "U3.1"}, t, false);
    }
    c.net("PMOD1_IO1", {"R9.2", "J2.1"}, std::nullopt);
    c.part("R10", "Device:R", "200R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C8218"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD1_SIG2");
        c.port("PMOD1_SIG2", {"R10.1", "U3.3"}, t, false);
    }
    c.net("PMOD1_IO2", {"R10.2", "J2.3"}, std::nullopt);
    c.part("R11", "Device:R", "200R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C8218"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD1_SIG3");
        c.port("PMOD1_SIG3", {"R11.1", "U3.6"}, t, false);
    }
    c.net("PMOD1_IO3", {"R11.2", "J2.5"}, std::nullopt);
    c.part("R12", "Device:R", "200R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C8218"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD1_SIG4");
        c.port("PMOD1_SIG4", {"R12.1", "U3.4"}, t, false);
    }
    c.net("PMOD1_IO4", {"R12.2", "J2.7"}, std::nullopt);
    c.part("R13", "Device:R", "200R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C8218"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD1_SIG5");
        c.port("PMOD1_SIG5", {"R13.1", "U4.1"}, t, false);
    }
    c.net("PMOD1_IO5", {"R13.2", "J2.2"}, std::nullopt);
    c.part("R14", "Device:R", "200R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C8218"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD1_SIG6");
        c.port("PMOD1_SIG6", {"R14.1", "U4.3"}, t, false);
    }
    c.net("PMOD1_IO6", {"R14.2", "J2.4"}, std::nullopt);
    c.part("R15", "Device:R", "200R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C8218"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD1_SIG7");
        c.port("PMOD1_SIG7", {"R15.1", "U4.6"}, t, false);
    }
    c.net("PMOD1_IO7", {"R15.2", "J2.6"}, std::nullopt);
    c.part("R16", "Device:R", "200R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C8218"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD1_SIG8");
        c.port("PMOD1_SIG8", {"R16.1", "U4.4"}, t, false);
    }
    c.net("PMOD1_IO8", {"R16.2", "J2.8"}, std::nullopt);
    c.part("C1", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.part("C2", "Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C15850"}});
    c.part("C3", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.part("C4", "Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C15850"}});
    c.net("+VCC_PMOD", {"J1.11", "J1.12", "J2.11", "J2.12", "C1.1", "C2.1", "C3.1", "C4.1"}, std::nullopt);
    c.net("GND", {"J1.9", "J1.10", "J2.9", "J2.10", "U1.2", "U2.2", "U3.2", "U4.2", "C1.2", "C2.2", "C3.2", "C4.2"}, std::nullopt);
    c.nc({"U1.5", "U2.5", "U3.5", "U4.5"});
    c.draws("+VCC_PMOD", 0.2, meta.note("draws", "2x Pmod module budget ~100 mA each"));
    return meta.finish(c);
}
} // namespace schgen::subsystem_builders
