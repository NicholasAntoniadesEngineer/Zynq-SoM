#include "schgen/subsystem_authoring.hpp"

namespace schgen::project_builders {
// Migrated construction operations from devkit_mini/subsystems/debug_boot/debug_boot.py.
CircuitSheetIr devkit_mini_debug_boot(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("debug_boot", "JTAG + SWD headers, boot-request DIP, reset", context);
    {
        AuthoringPartSelection p;
        p.ref = "J1";
        c.use_part("878311420", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "J2";
        p.value = "HX_JN1.27-2x5";
        c.use_part("HX_JN1.27-2x5_TP_H4.9", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "SW1";
        p.value = "DIP-4";
        c.use_part("DSHP04TSGER", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "SW2";
        p.value = "RESET";
        c.use_part("TS-1187A-B-A-B", p);
    }
    c.net("GND", {"J1.1", "J1.3", "J1.5", "J1.7", "J1.9", "J1.11", "J1.13"}, std::nullopt);
    c.net("+3V3", {"J1.2"}, std::nullopt);
    c.part("R1", "Device:R", "4k7", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23162"}});
    c.part("R2", "Device:R", "4k7", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23162"}});
    {
        AuthoringPort t;
        t.expect = "som_j1_connector";
        c.port("ZYNQ_TMS", {"J1.4", "R1.2"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "som_j1_connector";
        c.port("ZYNQ_TCK", {"J1.6"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "som_j1_connector";
        c.port("ZYNQ_TDO", {"J1.8"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "som_j1_connector";
        c.port("ZYNQ_TDI", {"J1.10", "R2.2"}, t, true);
    }
    c.net("+3V3", {"R1.1", "R2.1"}, std::nullopt);
    c.nc({"J1.12", "J1.14"});
    c.net("+3V3_SC", {"J2.1"}, std::nullopt);
    c.net("GND", {"J2.3", "J2.5", "J2.9"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "som_j1_connector";
        c.port("STM32_GPIO6", {"J2.2"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "som_j1_connector";
        c.port("STM32_GPIO5", {"J2.4"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "som_j1_connector";
        c.port("STM32_NRST", {"J2.10", "SW2.1", "SW2.2"}, t, true);
    }
    c.nc({"J2.6", "J2.7", "J2.8"});
    c.net("GND", {"SW2.3", "SW2.4"}, std::nullopt);
    c.part("R3", "Device:R", "100R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22775"}});
    {
        AuthoringPort t;
        t.expect = "som_j1_connector";
        c.port("STM32_BOOT0", {"SW1.1"}, t, true);
    }
    c.net("BOOT0_SET", {"SW1.8", "R3.2"}, std::nullopt);
    c.net("+3V3_SC", {"R3.1"}, std::nullopt);
    c.part("R4", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25804"}});
    c.part("R5", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25804"}});
    {
        AuthoringPort t;
        t.expect = "som_j1_connector";
        c.port("STM32_GPIO7", {"SW1.2", "R4.2"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "som_j1_connector";
        c.port("STM32_GPIO8", {"SW1.3", "R5.2"}, t, true);
    }
    c.net("GND", {"SW1.7", "SW1.6"}, std::nullopt);
    c.part("R6", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25804"}});
    c.net("BOOT_SPARE", {"SW1.4", "R6.2"}, std::nullopt);
    c.net("GND", {"SW1.5"}, std::nullopt);
    c.net("+3V3_SC", {"R4.1", "R5.1", "R6.1"}, std::nullopt);
    c.auto_ref("R");
    c.part("R7", "Device:R", "4k7", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23162"}});
    c.net("+3V3_SC", {"R7.1"}, std::nullopt);
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "scl";
        t.bus = "STM32_I2C2";
        t.speed_hz = 400000;
        t.expect = "som_j1_connector";
        c.port("STM32_I2C2_SCL", {"R7.2"}, t, true);
    }
    c.auto_ref("R");
    c.part("R8", "Device:R", "4k7", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23162"}});
    c.net("+3V3_SC", {"R8.1"}, std::nullopt);
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "sda";
        t.bus = "STM32_I2C2";
        t.speed_hz = 400000;
        t.expect = "som_j1_connector";
        c.port("STM32_I2C2_SDA", {"R8.2"}, t, true);
    }
    c.auto_ref("TP");
    c.part("TP1", "Connector:TestPoint", "SDIO_CLK", "TestPoint:TestPoint_Pad_D1.5mm", {{"BOM", "exclude"}});
    {
        AuthoringPort t;
        t.kind = "sd_bus";
        t.bus = "SDIO";
        t.level_v = 1.8;
        t.expect = "som_j1_connector";
        c.port("SDIO_CLK", {"TP1.1"}, t, true);
    }
    c.auto_ref("TP");
    c.part("TP2", "Connector:TestPoint", "SDIO_CMD", "TestPoint:TestPoint_Pad_D1.5mm", {{"BOM", "exclude"}});
    {
        AuthoringPort t;
        t.kind = "sd_bus";
        t.bus = "SDIO";
        t.level_v = 1.8;
        t.expect = "som_j1_connector";
        c.port("SDIO_CMD", {"TP2.1"}, t, true);
    }
    c.auto_ref("TP");
    c.part("TP3", "Connector:TestPoint", "VBUS_OUT_EN", "TestPoint:TestPoint_Pad_D1.5mm", {{"BOM", "exclude"}});
    {
        AuthoringPort t;
        t.expect = "som_j1_connector";
        c.port("VBUS_OUT_EN", {"TP3.1"}, t, true);
    }
    c.draws("+3V3_SC", 0.004, "BOOT0 strap ~2 mA closed + BOOTSEL pulls");
    c.draws("+3V3_SC", 0.0015, "2x4k7 STM32_I2C2 pull-ups");
    c.draws("+3V3", 0.002, "JTAG TMS/TDI 4k7 insurance pulls when driven");
    return meta.finish(c);
}
} // namespace schgen::project_builders
