#include "schgen/subsystem_authoring.hpp"

namespace schgen::project_builders {
// Migrated construction operations from carrier/subsystems/fmc/fmc.py.
CircuitSheetIr carrier_fmc(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("fmc", "SoM bank-35 IO breakout (2x20 2.54mm header, VADJ 2.5V)", context);
    c.part("J1", "Connector_Generic:Conn_02x20_Odd_Even", "Header_2x20_2.54mm", "Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical", {});
    {
        AuthoringPort t;
        c.port("FMC_CLK0_M2C_P", {"J1.3"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("FMC_CLK0_M2C_N", {"J1.4"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "FMC_CLK0_M2C_N";
        t.impedance = 100;
        t.expect = "som_j3/j1 bank-35 pin map (dossier fmc.md section 1, P3 linker)";
        c.port_type("FMC_CLK0_M2C_P", t);
    }
    {
        AuthoringPort t;
        c.port("FMC_CLK1_M2C_P", {"J1.5"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("FMC_CLK1_M2C_N", {"J1.6"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "FMC_CLK1_M2C_N";
        t.impedance = 100;
        t.expect = "som_j3/j1 bank-35 pin map (dossier fmc.md section 1, P3 linker)";
        c.port_type("FMC_CLK1_M2C_P", t);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA00_CC_P", {"J1.9"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA00_CC_N", {"J1.10"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "FMC_LA00_CC_N";
        t.impedance = 100;
        t.expect = "som_j3/j1 bank-35 pin map (dossier fmc.md section 1, P3 linker)";
        c.port_type("FMC_LA00_CC_P", t);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA01_CC_P", {"J1.11"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA01_CC_N", {"J1.12"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "FMC_LA01_CC_N";
        t.impedance = 100;
        t.expect = "som_j3/j1 bank-35 pin map (dossier fmc.md section 1, P3 linker)";
        c.port_type("FMC_LA01_CC_P", t);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA02_P", {"J1.13"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA02_N", {"J1.14"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "FMC_LA02_N";
        t.impedance = 100;
        t.expect = "som_j3/j1 bank-35 pin map (dossier fmc.md section 1, P3 linker)";
        c.port_type("FMC_LA02_P", t);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA03_P", {"J1.17"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA03_N", {"J1.18"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "FMC_LA03_N";
        t.impedance = 100;
        t.expect = "som_j3/j1 bank-35 pin map (dossier fmc.md section 1, P3 linker)";
        c.port_type("FMC_LA03_P", t);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA04_P", {"J1.19"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA04_N", {"J1.20"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "FMC_LA04_N";
        t.impedance = 100;
        t.expect = "som_j3/j1 bank-35 pin map (dossier fmc.md section 1, P3 linker)";
        c.port_type("FMC_LA04_P", t);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA05_P", {"J1.21"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA05_N", {"J1.22"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "FMC_LA05_N";
        t.impedance = 100;
        t.expect = "som_j3/j1 bank-35 pin map (dossier fmc.md section 1, P3 linker)";
        c.port_type("FMC_LA05_P", t);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA06_P", {"J1.25"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA06_N", {"J1.26"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "FMC_LA06_N";
        t.impedance = 100;
        t.expect = "som_j3/j1 bank-35 pin map (dossier fmc.md section 1, P3 linker)";
        c.port_type("FMC_LA06_P", t);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA07_P", {"J1.27"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA07_N", {"J1.28"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "FMC_LA07_N";
        t.impedance = 100;
        t.expect = "som_j3/j1 bank-35 pin map (dossier fmc.md section 1, P3 linker)";
        c.port_type("FMC_LA07_P", t);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA08_P", {"J1.29"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA08_N", {"J1.30"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "FMC_LA08_N";
        t.impedance = 100;
        t.expect = "som_j3/j1 bank-35 pin map (dossier fmc.md section 1, P3 linker)";
        c.port_type("FMC_LA08_P", t);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA09_P", {"J1.33"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA09_N", {"J1.34"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "FMC_LA09_N";
        t.impedance = 100;
        t.expect = "som_j3/j1 bank-35 pin map (dossier fmc.md section 1, P3 linker)";
        c.port_type("FMC_LA09_P", t);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA10_P", {"J1.35"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA10_N", {"J1.36"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "FMC_LA10_N";
        t.impedance = 100;
        t.expect = "som_j3/j1 bank-35 pin map (dossier fmc.md section 1, P3 linker)";
        c.port_type("FMC_LA10_P", t);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA11_P", {"J1.37"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("FMC_LA11_N", {"J1.38"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "FMC_LA11_N";
        t.impedance = 100;
        t.expect = "som_j3/j1 bank-35 pin map (dossier fmc.md section 1, P3 linker)";
        c.port_type("FMC_LA11_P", t);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        p.footprint = "TLV75725PDYDR:TLV75725PDYDR";
        c.use_part("TLV75725PDYDR", p);
    }
    c.part("C1", "Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C15850"}});
    c.part("C2", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.part("C3", "Device:C", "1u", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C15849"}});
    c.part("C4", "Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C15850"}});
    c.part("C5", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("+3V3", {"J1.1", "U1.1", "U1.3", "C1.1", "C2.1", "C3.1"}, std::nullopt);
    c.net("+2V5_VADJ", {"J1.2", "U1.5", "C4.1", "C5.1"}, std::nullopt);
    c.net("GND", {"J1.7", "J1.8", "J1.15", "J1.16", "J1.23", "J1.24", "J1.31", "J1.32", "J1.39", "J1.40", "U1.2", "U1.6", "C1.2", "C2.2", "C3.2", "C4.2", "C5.2"}, std::nullopt);
    c.nc({"U1.4"});
    c.testpoint("+2V5_VADJ", std::nullopt);
    c.draws("+3V3", 0.5, "bank-35 IO header +3V3 add-on allowance");
    c.draws("+2V5_VADJ", 0.35, "VADJ bank-35 VCCO budget (TLV75725 DYD 0.40 A envelope less ~0.05 A bank-35 VCCO)");
    return meta.finish(c);
}
} // namespace schgen::project_builders
