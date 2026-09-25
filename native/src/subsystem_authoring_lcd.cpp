#include "schgen/subsystem_authoring.hpp"

namespace schgen::subsystem_builders {
// Migrated construction operations from subsystems/lcd/lcd.py.
CircuitSheetIr lcd(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("lcd", "40-pin TTL RGB LCD + SY7201 backlight boost", context);
    {
        AuthoringPartSelection p;
        p.ref = "J1";
        c.use_part("AFC07-S40FCA-00", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        c.use_part("SY7201ABC", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "L1";
        p.value = "10uH";
        c.use_part("SWPA4030S100MT", p);
    }
    c.part("D1", "Device:D_Schottky", "SS34", "Diode_SMD:D_SMA", {{"LCSC", "C8678"}});
    c.part("R1", "Device:R", "1.5R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22769"}});
    c.part("C1", "Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C15850"}});
    c.part("C2", "Device:C", "2.2u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C125847"}});
    c.part("C3", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_R0");
        c.port("LCD_R0", {"J1.5"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_R1");
        c.port("LCD_R1", {"J1.6"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_R2");
        c.port("LCD_R2", {"J1.7"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_R3");
        c.port("LCD_R3", {"J1.8"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_R4");
        c.port("LCD_R4", {"J1.9"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_R5");
        c.port("LCD_R5", {"J1.10"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_R6");
        c.port("LCD_R6", {"J1.11"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_R7");
        c.port("LCD_R7", {"J1.12"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_G0");
        c.port("LCD_G0", {"J1.13"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_G1");
        c.port("LCD_G1", {"J1.14"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_G2");
        c.port("LCD_G2", {"J1.15"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_G3");
        c.port("LCD_G3", {"J1.16"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_G4");
        c.port("LCD_G4", {"J1.17"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_G5");
        c.port("LCD_G5", {"J1.18"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_G6");
        c.port("LCD_G6", {"J1.19"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_G7");
        c.port("LCD_G7", {"J1.20"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_B0");
        c.port("LCD_B0", {"J1.21"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_B1");
        c.port("LCD_B1", {"J1.22"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_B2");
        c.port("LCD_B2", {"J1.23"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_B3");
        c.port("LCD_B3", {"J1.24"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_B4");
        c.port("LCD_B4", {"J1.25"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_B5");
        c.port("LCD_B5", {"J1.26"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_B6");
        c.port("LCD_B6", {"J1.27"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_B7");
        c.port("LCD_B7", {"J1.28"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_DISP");
        c.port("LCD_DISP", {"J1.31"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_HSYNC");
        c.port("LCD_HSYNC", {"J1.32"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_VSYNC");
        c.port("LCD_VSYNC", {"J1.33"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_DE");
        c.port("LCD_DE", {"J1.34"}, t, false);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U2";
        c.use_part("USBLC6-2SC6", p);
    }
    c.net("CTP_SDA_FFC", {"J1.37", "U2.1"}, std::nullopt);
    c.net("CTP_SCL_FFC", {"J1.38", "U2.3"}, std::nullopt);
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "sda";
        t.bus = meta.bus("i2c", "LCD_CTP");
        t.speed_hz = 400000;
        t.expect = meta.expect_kw("TP_SDA");
        c.port("TP_SDA", {"U2.6"}, t, true);
    }
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "scl";
        t.bus = meta.bus("i2c", "LCD_CTP");
        t.speed_hz = 400000;
        t.expect = meta.expect_kw("TP_SCL");
        c.port("TP_SCL", {"U2.4"}, t, true);
    }
    c.net("+VDD_TP_CLAMP", {"U2.5"}, std::nullopt);
    c.net("GND", {"U2.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("TP_RST");
        c.port("TP_RST", {"J1.39"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("TP_INT");
        c.port("TP_INT", {"J1.40"}, t, false);
    }
    c.part("R2", "Device:R", "4k7", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23162"}});
    c.net("TP_SDA", {"R2.1"}, std::nullopt);
    c.net("+VDD_LCD", {"R2.2"}, std::nullopt);
    c.part("R3", "Device:R", "4k7", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23162"}});
    c.net("TP_SCL", {"R3.1"}, std::nullopt);
    c.net("+VDD_LCD", {"R3.2"}, std::nullopt);
    c.part("R5", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("TP_RST", {"R5.1"}, std::nullopt);
    c.net("GND", {"R5.2"}, std::nullopt);
    c.part("R6", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25804"}});
    c.net("LCD_DISP", {"R6.1"}, std::nullopt);
    c.net("+VDD_LCD", {"R6.2"}, std::nullopt);
    c.part("R7", "Device:R", "22R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23345"}});
    c.net("LCD_PCLK_PANEL", {"J1.30", "R7.1"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("LCD_PCLK");
        c.port("LCD_PCLK", {"R7.2"}, t, false);
    }
    c.net("+VDD_LCD", {"J1.4", "C3.1"}, std::nullopt);
    c.net("GND", {"J1.3", "J1.29", "J1.36", "C3.2"}, std::nullopt);
    c.nc({"J1.35", "J1.41", "J1.42"});
    c.auto_ref("C");
    c.part("C4", "Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C15850"}});
    c.net("+VDD_LCD", {"C4.1"}, std::nullopt);
    c.net("GND", {"C4.2"}, std::nullopt);
    c.auto_ref("C");
    c.part("C5", "Device:C", "1u", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C15849"}});
    c.net("+VBOOST_IN", {"U1.IN", "L1.1", "C1.1", "C5.1"}, std::nullopt);
    c.net("GND", {"U1.GND", "C1.2", "C2.2", "R1.2", "C5.2"}, std::nullopt);
    c.net("LCD_BL_SW", {"L1.2", "U1.LX"}, std::nullopt);
    c.net("LCD_VLED_P", {"D1.1", "C2.1", "U1.OVP", "J1.2"}, std::nullopt);
    c.net("LCD_BL_SW", {"D1.2"}, std::nullopt);
    c.net("LCD_VLED_N", {"J1.1", "R1.1", "U1.FB"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("BL_PWM");
        c.port("BL_PWM", {"U1.EN/PWM"}, t, false);
    }
    c.part("R4", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("BL_PWM", {"R4.1"}, std::nullopt);
    c.net("GND", {"R4.2"}, std::nullopt);
    c.testpoint("+VBOOST_IN", std::nullopt);
    c.testpoint("TP_SDA", std::nullopt);
    c.testpoint("TP_SCL", std::nullopt);
    c.draws("+VDD_LCD", 0.1, meta.note("draws_lcd", "panel logic 25-75 mA + touch <= 25 mA"));
    c.draws("+VBOOST_IN", 0.45, meta.note("draws_boost", "SY7201 boost input @133 mA LED string (operating point + margin)"));
    c.waive("reset_waivers", "TP_RST", "GPIO-driven reset, held by 100k pull-down until PL releases");
    c.waive("part_rule_waivers", "C2", "MLCC 50V on LCD_VLED_P: the 30V is the rare open-LED OVP-clamp transient, not continuous (string ~9.6V); 50V/X7R dossier-sized for it (lcd_backlight.md). 2x derate targets continuous DC bias, not a fault clamp");
    return meta.finish(c);
}
} // namespace schgen::subsystem_builders
