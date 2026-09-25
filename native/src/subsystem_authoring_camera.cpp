#include "schgen/subsystem_authoring.hpp"

namespace schgen::subsystem_builders {
// Migrated construction operations from subsystems/camera/camera.py.
CircuitSheetIr camera(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("camera", "RPi camera port: 2-lane MIPI CSI-2 (15P FFC)", context);
    {
        AuthoringPartSelection p;
        p.ref = "J1";
        c.use_part("SFW15R-1STE1LF", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        c.use_part("TPD4E02B04DQAR", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U2";
        c.use_part("TPD4E02B04DQAR", p);
    }
    c.part("R1", "Device:R", "100R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22775"}});
    {
        AuthoringPort t;
        c.port("CSI_D0_P", {"J1.3", "R1.1", "U1.IO1"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("CSI_D0_N", {"J1.2", "R1.2", "U1.IO2"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "CSI_D0_N";
        t.impedance = 100;
        t.expect = meta.expect("CSI_D0_P", "host MIPI CSI-2 receiver (diff_pair @100R, LVDS-class lanes)");
        c.port_type("CSI_D0_P", t);
    }
    c.part("R2", "Device:R", "100R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22775"}});
    {
        AuthoringPort t;
        c.port("CSI_D1_P", {"J1.6", "R2.1", "U1.IO3"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("CSI_D1_N", {"J1.5", "R2.2", "U1.IO4"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "CSI_D1_N";
        t.impedance = 100;
        t.expect = meta.expect("CSI_D1_P", "host MIPI CSI-2 receiver (diff_pair @100R, LVDS-class lanes)");
        c.port_type("CSI_D1_P", t);
    }
    c.part("R3", "Device:R", "100R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22775"}});
    {
        AuthoringPort t;
        c.port("CSI_CLK_P", {"J1.9", "R3.1", "U2.IO1"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("CSI_CLK_N", {"J1.8", "R3.2", "U2.IO2"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "diff_pair";
        t.pair_with = "CSI_CLK_N";
        t.impedance = 100;
        t.expect = meta.expect("CSI_CLK_P", "host MIPI CSI-2 receiver (diff_pair @100R, LVDS-class lanes)");
        c.port_type("CSI_CLK_P", t);
    }
    c.net("GND", {"U1.GND", "U2.GND"}, std::nullopt);
    c.nc({"U1.6", "U1.7", "U1.9", "U1.10"});
    c.nc({"U2.6", "U2.7", "U2.9", "U2.10"});
    c.part("R4", "Device:R", "4k7", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23162"}});
    c.part("R5", "Device:R", "4k7", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23162"}});
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "scl";
        t.bus = meta.bus("i2c", "CAM_CCI");
        t.speed_hz = 400000;
        t.expect = meta.expect_kw("CAM_SCL");
        c.port("CAM_SCL", {"J1.13", "R4.2", "U2.4"}, t, true);
    }
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "sda";
        t.bus = meta.bus("i2c", "CAM_CCI");
        t.speed_hz = 400000;
        t.expect = meta.expect_kw("CAM_SDA");
        c.port("CAM_SDA", {"J1.14", "R5.2", "U2.5"}, t, true);
    }
    c.net("+VDD_CAM", {"R4.1", "R5.1"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("CAM_EN");
        c.port("CAM_EN", {"J1.11"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("CAM_LED");
        c.port("CAM_LED", {"J1.12"}, t, false);
    }
    c.part("C1", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.part("C2", "Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C15850"}});
    c.net("+VDD_CAM", {"J1.15", "C1.1", "C2.1"}, std::nullopt);
    c.net("GND", {"J1.1", "J1.4", "J1.7", "J1.10", "C1.2", "C2.2", "J1.16", "J1.17"}, std::nullopt);
    c.testpoint("CAM_SCL", std::nullopt);
    c.testpoint("CAM_SDA", std::nullopt);
    c.testpoint("CAM_EN", std::nullopt);
    c.draws("+VDD_CAM", 0.3, meta.note("draws", "RPi camera module budget (V2/IMX219 typ ~250 mA incl. I2C pull-ups)"));
    return meta.finish(c);
}
} // namespace schgen::subsystem_builders
