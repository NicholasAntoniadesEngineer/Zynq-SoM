#include "schgen/subsystem_authoring.hpp"

namespace schgen::subsystem_builders {
// Migrated construction operations from subsystems/microsd/microsd.py.
CircuitSheetIr microsd(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("microsd", "microSD slot (1.8V SoM <-> 3.3V card, TXS02612)", context);
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        c.use_part("TXS02612RTWR", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "J1";
        c.use_part("TF-01A", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U2";
        c.use_part("TPD6E001RSER", p);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("SD_CLK");
        c.port("SD_CLK", {"U1.CLKA"}, t, false);
    }
    c.net("SD_CARD_CLK", {"U1.CLKB0", "J1.CLK(SCLK)", "U2.IO1"}, std::nullopt);
    {
        AuthoringPort t;
        t.kind = "sd_bus";
        t.level_v = 1.8;
        c.port_type("SD_CLK", t);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("SD_CMD");
        c.port("SD_CMD", {"U1.CMDA"}, t, false);
    }
    c.net("SD_CARD_CMD", {"U1.CMDB0", "J1.CMD(DI)", "U2.IO2"}, std::nullopt);
    {
        AuthoringPort t;
        t.kind = "sd_bus";
        t.level_v = 1.8;
        c.port_type("SD_CMD", t);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("SD_D0");
        c.port("SD_D0", {"U1.DAT0A"}, t, false);
    }
    c.net("SD_CARD_D0", {"U1.DAT0B0", "J1.DAT0(D0)", "U2.IO3"}, std::nullopt);
    {
        AuthoringPort t;
        t.kind = "sd_bus";
        t.level_v = 1.8;
        c.port_type("SD_D0", t);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("SD_D1");
        c.port("SD_D1", {"U1.DAT1A"}, t, false);
    }
    c.net("SD_CARD_D1", {"U1.DAT1B0", "J1.DAT1(RSV)", "U2.IO4"}, std::nullopt);
    {
        AuthoringPort t;
        t.kind = "sd_bus";
        t.level_v = 1.8;
        c.port_type("SD_D1", t);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("SD_D2");
        c.port("SD_D2", {"U1.DAT2A"}, t, false);
    }
    c.net("SD_CARD_D2", {"U1.DAT2B0", "J1.DAT2(RSV)", "U2.IO5"}, std::nullopt);
    {
        AuthoringPort t;
        t.kind = "sd_bus";
        t.level_v = 1.8;
        c.port_type("SD_D2", t);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("SD_D3");
        c.port("SD_D3", {"U1.DAT3A"}, t, false);
    }
    c.net("SD_CARD_D3", {"U1.DAT3B0", "J1.CDDAT3(CS)", "U2.IO6"}, std::nullopt);
    {
        AuthoringPort t;
        t.kind = "sd_bus";
        t.level_v = 1.8;
        c.port_type("SD_D3", t);
    }
    c.part("R1", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("SD_CARD_CMD", {"R1.2"}, std::nullopt);
    c.part("R2", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("SD_CARD_D0", {"R2.2"}, std::nullopt);
    c.part("R3", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("SD_CARD_D1", {"R3.2"}, std::nullopt);
    c.part("R4", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("SD_CARD_D2", {"R4.2"}, std::nullopt);
    c.part("R5", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("SD_CARD_D3", {"R5.2"}, std::nullopt);
    c.part("R6", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25804"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("CD_N");
        c.port("CD_N", {"J1.CD", "R6.2"}, t, false);
    }
    c.net("+VDD_HOST", {"U1.VCCA"}, std::nullopt);
    c.decouple("U1.VCCA", {"100n"}, std::nullopt, "GND", "Device:C", "");
    c.part("C2", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.part("C3", "Device:C", "22u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C45783"}});
    c.net("+VDD_CARD", {"J1.VDD", "U1.VCCB0", "U1.VCCB1", "C2.1", "C3.1", "U2.VCC", "R1.1", "R2.1", "R3.1", "R4.1", "R5.1", "R6.1"}, std::nullopt);
    c.net("GND", {"C2.2", "C3.2"}, std::nullopt);
    c.decouple("U2.VCC", {"100n"}, std::nullopt, "GND", "Device:C", "");
    c.net("GND", {"U1.SEL", "U1.EP", "U1.GND", "J1.VSS", "J1.GND", "U2.GND"}, std::nullopt);
    c.nc({"U1.DAT2B1", "U1.DAT3B1", "U1.CMDB1", "U1.CLKB1", "U1.DAT0B1", "U1.DAT1B1"});
    c.nc({"U2.NC"});
    c.testpoint("SD_CMD", std::nullopt);
    c.testpoint("SD_CLK", std::nullopt);
    c.draws("+VDD_CARD", 0.25, meta.note("draws_card", "SD card write burst ~200 mA + pull-ups + TXS02612 VCCB"));
    c.draws("+VDD_HOST", 0.005, meta.note("draws_host", "TXS02612 VCCA (host-side level)"));
    c.field("C1", "LCSC", "C14663");
    c.field("C4", "LCSC", "C14663");
    return meta.finish(c);
}
} // namespace schgen::subsystem_builders
