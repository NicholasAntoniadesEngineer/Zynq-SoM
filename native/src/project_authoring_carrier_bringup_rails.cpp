#include "schgen/subsystem_authoring.hpp"

namespace schgen::project_builders {
// Migrated construction operations from carrier/subsystems/bringup_rails/bringup_rails.py.
CircuitSheetIr carrier_bringup_rails(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("bringup_rails", "Bring-up controls: rail/module DIPs + TCA9535 + buttons", context);
    {
        AuthoringPartSelection p;
        p.ref = "SW1";
        c.use_part("DSHP04TSGER", p);
    }
    c.net("+3V3_SC", {"SW1.1", "SW1.3", "SW1.5", "SW1.7"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_DIP_5V0", {"SW1.8"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_DIP_3V3", {"SW1.2"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_DIP_1V8", {"SW1.6"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_DIP_USER_LED", {"SW1.4"}, t, true);
    }
    {
        AuthoringPartSelection p;
        p.ref = "SW2";
        c.use_part("DSHP08TSGER", p);
    }
    c.net("+3V3_SC", {"SW2.1", "SW2.2", "SW2.3", "SW2.4", "SW2.5", "SW2.6", "SW2.7", "SW2.8"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_DIP_HDMI_TX", {"SW2.9"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_DIP_HDMI_RX", {"SW2.10"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_DIP_LCD", {"SW2.11"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_DIP_CAM", {"SW2.12"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_DIP_SD", {"SW2.13"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_DIP_USB", {"SW2.14"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_DIP_PMOD", {"SW2.15"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_DIP_SPARE", {"SW2.16"}, t, true);
    }
    {
        AuthoringPartSelection p;
        p.ref = "SW6";
        c.use_part("DSHP04TSGER", p);
    }
    c.net("+3V3_SC", {"SW6.1", "SW6.3", "SW6.5", "SW6.7"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_DIP_HDMI_TX_5V", {"SW6.8"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_DIP_LCD_5V", {"SW6.2"}, t, true);
    }
    c.nc({"SW6.4", "SW6.6"});
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        c.use_part("TCA9535PWR", p);
    }
    c.net("+3V3_SC", {"U1.VCC"}, std::nullopt);
    c.decouple("U1.VCC", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.net("GND", {"U1.GND", "U1.A1", "U1.A2", "U1.A0"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_OVR_HDMI_TX", {"U1.P00"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_OVR_HDMI_RX", {"U1.P01"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_OVR_LCD", {"U1.P02"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_OVR_CAM", {"U1.P03"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_OVR_SD", {"U1.P04"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_OVR_USB", {"U1.P05"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_OVR_PMOD", {"U1.P06"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_OVR_USER_LED", {"U1.P07"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_OVR_LCD_BL", {"U1.P10"}, t, true);
    }
    c.auto_ref("R");
    c.part("R1", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("BU_OVR_LCD_BL", {"R1.1"}, std::nullopt);
    c.net("GND", {"R1.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_OVR_HDMI_TX_5V", {"U1.P12"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)";
        c.port("BU_OVR_LCD_5V", {"U1.P13"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "power_mon (INA3221 CRITICAL wire-OR, 10k PU +3V3_SC)";
        c.port("PMON_ALERT_N", {"U1.P11"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "usbc_otg (TPS2051C FLT#, 100k PU +3V3_SC)";
        c.port("USBOTG_FLT_N", {"U1.P14"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "pd_input (TPS26631 eFuse FLT#, 100k PU +3V3_SC)";
        c.port("PD_FLT_N", {"U1.P15"}, t, true);
    }
    c.auto_ref("R");
    c.part("R2", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("BU_P16", {"U1.P16", "R2.1"}, std::nullopt);
    c.net("GND", {"R2.2"}, std::nullopt);
    c.auto_ref("R");
    c.part("R3", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("BU_P17", {"U1.P17", "R3.1"}, std::nullopt);
    c.net("GND", {"R3.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "scl";
        t.bus = "STM32_I2C2";
        t.speed_hz = 400000;
        t.expect = "som_j3_connector (wave 3 STM32 GPIO function map)";
        c.port("STM32_I2C2_SCL", {"U1.SCL"}, t, true);
    }
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "sda";
        t.bus = "STM32_I2C2";
        t.speed_hz = 400000;
        t.expect = "som_j3_connector (wave 3 STM32 GPIO function map)";
        c.port("STM32_I2C2_SDA", {"U1.SDA"}, t, true);
    }
    c.pullup("U1.SCL", "4k7", "+3V3_SC", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    c.pullup("U1.SDA", "4k7", "+3V3_SC", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    {
        AuthoringPort t;
        t.expect = "som_j3_connector (wave 3 STM32 GPIO function map)";
        c.port("SC_INT_N", {"U1.INT#"}, t, true);
    }
    c.pullup("U1.INT#", "10k", "+3V3_SC", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    {
        AuthoringPartSelection p;
        p.ref = "SW3";
        c.use_part("TS-1187A-B-A-B", p);
    }
    c.auto_ref("C");
    c.part("C2", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    {
        AuthoringPort t;
        t.expect = "som_j1_j2 bank-33 PL pin assignment (P3 linker)";
        c.port("PL_BTN0", {"SW3.1", "SW3.2", "C2.1"}, t, true);
    }
    c.net("GND", {"SW3.3", "SW3.4", "C2.2"}, std::nullopt);
    c.pullup("SW3.1", "10k", "+3V3", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    {
        AuthoringPartSelection p;
        p.ref = "SW4";
        c.use_part("TS-1187A-B-A-B", p);
    }
    c.auto_ref("C");
    c.part("C3", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    {
        AuthoringPort t;
        t.expect = "som_j1_j2 bank-33 PL pin assignment (P3 linker)";
        c.port("PL_BTN1", {"SW4.1", "SW4.2", "C3.1"}, t, true);
    }
    c.net("GND", {"SW4.3", "SW4.4", "C3.2"}, std::nullopt);
    c.pullup("SW4.1", "10k", "+3V3", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    {
        AuthoringPartSelection p;
        p.ref = "SW5";
        c.use_part("TS-1187A-B-A-B", p);
    }
    c.auto_ref("C");
    c.part("C4", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    {
        AuthoringPort t;
        c.port("STM32_NRST", {"SW5.1", "SW5.2", "C4.1"}, t, false);
    }
    c.net("GND", {"SW5.3", "SW5.4", "C4.2"}, std::nullopt);
    c.auto_ref("R");
    c.part("R9", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25804"}});
    {
        AuthoringPort t;
        t.expect = "som_j3_connector (wave 3 STM32 GPIO function map)";
        c.port("PUDC_34", {"R9.2"}, t, true);
    }
    c.net("GND", {"R9.1"}, std::nullopt);
    c.testpoint("+3V3_SC", std::nullopt);
    c.testpoint("STM32_I2C2_SDA", std::nullopt);
    c.testpoint("STM32_I2C2_SCL", std::nullopt);
    c.draws("+3V3_SC", 0.005, "TCA9535 + DIP/I2C/INT pull networks (dossier R3 < 5 mA)");
    c.draws("+3V3", 0.001, "2x user-button 10k pull-ups when pressed");
    c.field("C1", "LCSC", "C14663");
    c.field("R4", "LCSC", "C23162");
    c.field("R5", "LCSC", "C23162");
    c.field("R6", "LCSC", "C25804");
    c.field("R7", "LCSC", "C25804");
    c.field("R8", "LCSC", "C25804");
    return meta.finish(c);
}
} // namespace schgen::project_builders
