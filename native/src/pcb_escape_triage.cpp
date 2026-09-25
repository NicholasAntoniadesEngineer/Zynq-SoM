#include "pcb_escape_internal.hpp"

namespace schgen {
PcbEscapeSignalClass classify_pcb_escape_signal(const std::string &net,
                                                const ProjectStrings &mapping) {
    using namespace pcb_checks;
    // Ordered curated policy, not inferred from net tokens or a speed default.
    // Immutable regexes are safe to share; the caller's mapping is never cached.
    struct Rule {
        std::regex pattern;
        const char *klass;
        const char *basis;
    };
    static const std::vector<Rule> rules = {
        {std::regex(R"(HDMI_RX_(D\d|CLK)_[PN])"), "GENUINE",
         "TMDS sink lane, 742.5 Mbps/lane at 720p60 — eye budget is real"},
        {std::regex(R"(ZYNQ_HDMI_TX_TMDS_(\d|CLK)_[PN])"), "GENUINE",
         "TMDS source lane, 742.5 Mbps/lane at 720p60 — eye budget is real"},
        {std::regex(R"(ETH_PHY_MDI\d_[PN])"), "GENUINE",
         "100BASE-TX MDI pair, 125 MBd MLT-3 through the mated interface"},
        {std::regex(R"(CAM_(D\d|CLK)_[PN])"), "GENUINE",
         "CSI-2 D-PHY lane (LVDS_25 on bank 35) — sub-ns edges"},
        {std::regex(R"(USB_D[+-])"), "GENUINE",
         "USB 2.0 HS 480 Mbps PS-OTG pair — safe-direction high (not among the 69 v1 P/N-token "
         "pairs; class affects ordering only)"},
        {std::regex(R"(FMC_(LA\d\d(_CC)?|CLK\d_M2C)_[PN])"), "MODERATE",
         "FMC LVDS user pair (LVDS_25) — speed set by the mezzanine, budget relaxed vs TMDS"},
        {std::regex(R"(STM32_USB_D_[PN])"), "MODERATE",
         "USB full-speed 12 Mbps device pair — edges matter, budget generous"},
        {std::regex(R"(LCD_(R|G|B)\d)"), "MODERATE",
         "LCD parallel RGB data @ ~33 MHz pixel clock, simultaneous-switching bus"},
        {std::regex(R"(LCD_(PCLK|HSYNC|VSYNC|DE))"), "MODERATE",
         "LCD pixel clock / sync — the timing edge of the parallel RGB bus"},
        {std::regex(R"(LCD_CTP_(SDA|SCL|INT|RST))"), "LOW",
         "capacitive-touch-panel I2C + control — 400 kHz class"},
        {std::regex(R"(LCD_(BL_PWM|DISP))"), "LOW", "LCD backlight PWM / display-enable control"},
        {std::regex(R"(PMODX?_IO\d)"), "LOW", "PMOD expansion header GPIO"},
        {std::regex(R"(IO_(L\d.*|\d+_\d+|0_\d+))"), "LOW",
         "unclaimed SoM contract GPIO (pmod/user_io headers — no function sheet)"},
        {std::regex(R"(DBG_UART_(RXD|TXD))"), "LOW", "debug UART, <= 1 MBd"},
        {std::regex(R"(ZYNQ_PS_UART0_(RXD|TXD|CTS_N|RTS_N))"), "LOW", "PS UART + flow control"},
        {std::regex(R"(ESC_(PWM_IN\d|BUF_OE_N|FAULT_N))"), "LOW",
         "ESC PWM (50-490 Hz class) + buffer control"},
        {std::regex(R"(ETH_LED\d)"), "LOW", "PHY LED indicator"},
        {std::regex(R"(CAM_(EN|LED|SCL|SDA))"), "LOW", "camera control / SCCB I2C"},
        {std::regex(R"(HDMI_RX_(CEC|5V_DET))"), "LOW", "HDMI CEC (kHz) / cable-detect level"},
        {std::regex(R"(ZYNQ_HDMI_TX_(CEC|HPD|SCL|SDA))"), "LOW",
         "HDMI CEC / hot-plug / DDC I2C — 100 kHz class"},
        {std::regex(R"(SDIO_(CLK|CMD|D\d))"), "LOW",
         "SDIO @ 50 MHz single-ended, short reach, terminated at the SoM"},
        {std::regex(R"(SD_CARD_DETECT)"), "LOW", "card-detect level"},
        {std::regex(R"(STM32_(BOOT0|NRST|GPIO\d|I2C2_SCL|I2C2_SDA|RAIL_EN_\dV\d|USB_CC\d))"), "LOW",
         "supervisor control / I2C / CC lines"},
        {std::regex(R"(ZYNQ_PS_MIO\d+([/\\]VM\d)?)"), "LOW", "PS MIO GPIO / voltage-monitor strap"},
        {std::regex(R"(ZYNQ_T(CK|DI|DO|MS))"), "LOW", "JTAG — held static outside debug"},
        {std::regex(R"((WATCHDOG_(KICK|RST_N)|SC_INT_N|PL_BTN\d|PUDC_\d+))"), "LOW",
         "supervisor watchdog / interrupt / button / pull-up-during-config strap"},
        {std::regex(R"((USB_ID|USB_VBUS|VBUS_OUT_EN))"), "LOW", "USB OTG ID / VBUS sense + enable"},
        {std::regex(R"(VIN)"), "LOW",
         "power inlet leaked under a signal-style name (no '+' prefix) — carried by planes, not "
         "lanes"},
    };
    const auto it =
        std::find_if(mapping.begin(), mapping.end(), [&](const auto &p) { return p.first == net; });
    const auto function = it == mapping.end() ? net : it->second;
    for (const auto &r : rules)
        if (std::regex_match(function, r.pattern))
            return {net, function, r.klass, r.basis};
    throw PcbEscapeError("uncurated DF40 signal net " + repr(net) + " (function " + repr(function) +
                         ") — add a curated class row to schgen/verify/si_triage.py (LAW 7: never "
                         "a silent default)");
}
} // namespace schgen
