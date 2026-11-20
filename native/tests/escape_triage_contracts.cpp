#include "schgen/pcb_escape.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

namespace {

using namespace schgen;
namespace fs = std::filesystem;

std::size_t checks = 0;
const std::size_t minimum_named_nets = 10;

void require(bool condition, const std::string& detail) {
    ++checks;
    if (!condition) throw std::runtime_error(detail);
}

template <class Call> void rejects(Call call, const std::string& needle) {
    bool thrown = false;
    try {
        call();
    } catch (const std::runtime_error& error) {
        thrown = std::string(error.what()).find(needle) != std::string::npos;
        if (!thrown) throw std::runtime_error("expected '" + needle + "', got: " + error.what());
    }
    require(thrown, "accepted: expected '" + needle + "'");
}

struct Scratch {
    fs::path root;
    Scratch() : root(fs::temp_directory_path() / "schgen_escape_triage_contracts") {
        fs::remove_all(root);
        fs::create_directories(root);
    }
    ~Scratch() { fs::remove_all(root); }
    PcbEscapeTriage load(const std::string& text) const {
        std::ofstream(root / "escape_triage.json", std::ios::binary) << text;
        return load_escape_triage(root);
    }
};

std::string rule_file(const std::string& rows) {
    return R"({"schema": "schgen.escape_triage/1", "rules": [)" + rows + "]}";
}

std::string row(const std::string& pattern, const std::string& klass, const std::string& note) {
    return R"({"pattern": ")" + pattern + R"(", "class": ")" + klass + R"(", "note": ")" + note + R"("})";
}

void real_files_load(const fs::path& repository) {
    const auto carrier = load_escape_triage(repository / "carrier");
    const auto devkit = load_escape_triage(repository / "devkit_mini");
    require(!carrier.rules.empty(), "carrier has no rules");
    require(carrier.rules.size() == devkit.rules.size(), "boards differ in rule count");
    for (std::size_t i = 0; i < carrier.rules.size(); ++i)
        require(carrier.rules[i].source == devkit.rules[i].source &&
                    carrier.rules[i].klass == devkit.rules[i].klass &&
                    carrier.rules[i].note == devkit.rules[i].note,
                "boards differ at rule " + std::to_string(i));
}

void first_match_wins(const Scratch& scratch) {
    const auto triage = scratch.load(rule_file(row("AB.*", "LOW", "first") + "," + row("ABC", "GENUINE", "second")));
    const auto found = classify_pcb_escape_signal("ABC", {}, triage);
    require(found.klass == "LOW" && found.basis == "first", "second rule won over the first");
    require(found.net == "ABC" && found.function == "ABC", "net and function not carried");
}

void full_match_only(const Scratch& scratch) {
    const auto triage = scratch.load(rule_file(row("ABC", "LOW", "whole")));
    rejects([&] { classify_pcb_escape_signal("XABC", {}, triage); }, "uncurated DF40 signal net");
    rejects([&] { classify_pcb_escape_signal("ABCX", {}, triage); }, "uncurated DF40 signal net");
}

void unmatched_net_has_no_default(const Scratch& scratch) {
    const auto triage = scratch.load(rule_file(row("ABC", "LOW", "whole")));
    rejects([&] { classify_pcb_escape_signal("NO_SUCH_NET", {}, triage); }, "uncurated DF40 signal net");
    rejects([&] { classify_pcb_escape_signal("ABC", {}, PcbEscapeTriage{}); }, "uncurated DF40 signal net");
}

void function_map_is_applied(const Scratch& scratch) {
    const auto triage = scratch.load(rule_file(row("FUNC", "MODERATE", "mapped")));
    const ProjectStrings mapping{{"RAW", "FUNC"}};
    const auto found = classify_pcb_escape_signal("RAW", mapping, triage);
    require(found.net == "RAW" && found.function == "FUNC" && found.klass == "MODERATE", "mapping not applied");
    rejects([&] { classify_pcb_escape_signal("FUNC_X", mapping, triage); }, "uncurated DF40 signal net");
}

void rejections(const Scratch& scratch) {
    const std::string good = row("A", "LOW", "n");
    rejects([&] { load_escape_triage(scratch.root / "absent"); }, "file is missing");
    rejects([&] { scratch.load(R"({"rules": [)" + good + "]}"); }, "missing required field 'schema'");
    rejects([&] { scratch.load(R"({"schema": "schgen.escape_triage/2", "rules": [)" + good + "]}"); }, "schema is not");
    rejects([&] { scratch.load(R"({"schema": "schgen.escape_triage/1"})"); }, "'rules' is missing");
    rejects([&] { scratch.load(rule_file("")); }, "'rules' is empty");
    rejects([&] { scratch.load(R"({"schema": "schgen.escape_triage/1", "rules": [], "default": "LOW"})"); },
            "unknown key 'default'");
    rejects([&] { scratch.load(rule_file(R"({"pattern": "A", "class": "LOW", "note": "n", "extra": 1})")); },
            "unknown key 'extra'");
    rejects([&] { scratch.load(rule_file(row("", "LOW", "n"))); }, "field 'pattern' must not be empty");
    rejects([&] { scratch.load(rule_file(R"({"class": "LOW", "note": "n"})")); }, "missing required field 'pattern'");
    rejects([&] { scratch.load(rule_file(row("A", "", "n"))); }, "field 'class' must not be empty");
    rejects([&] { scratch.load(rule_file(R"({"pattern": "A", "note": "n"})")); }, "missing required field 'class'");
    rejects([&] { scratch.load(rule_file(row("A", "LOW", ""))); }, "field 'note' must not be empty");
    rejects([&] { scratch.load(rule_file(R"({"pattern": "A", "class": "LOW"})")); }, "missing required field 'note'");
    rejects([&] { scratch.load(rule_file(row("(unclosed", "LOW", "n"))); }, "(unclosed");
    rejects([&] { scratch.load(rule_file(row("(unclosed", "LOW", "n"))); }, "escape_triage.json");
    rejects([&] { scratch.load(rule_file(row("A", "CRITICAL", "n"))); }, "unknown class CRITICAL");
    rejects([&] { scratch.load(rule_file(row("A", "low", "n"))); }, "unknown class low");
}

struct Expectation {
    const char* net;
    const char* klass;
    const char* note;
};

void carrier_classification(const fs::path& repository) {
    const auto triage = load_escape_triage(repository / "carrier");
    const std::vector<Expectation> expected = {
        {"HDMI_RX_D0_P", "GENUINE", "TMDS sink lane, 742.5 Mbps/lane at 720p60 \xE2\x80\x94 eye budget is real"},
        {"ZYNQ_HDMI_TX_TMDS_CLK_N", "GENUINE", "TMDS source lane, 742.5 Mbps/lane at 720p60 \xE2\x80\x94 eye budget is real"},
        {"ETH_PHY_MDI1_P", "GENUINE", "100BASE-TX MDI pair, 125 MBd MLT-3 through the mated interface"},
        {"CAM_CLK_N", "GENUINE", "CSI-2 D-PHY lane (LVDS_25 on bank 35) \xE2\x80\x94 sub-ns edges"},
        {"USB_D+", "GENUINE",
         "USB 2.0 HS 480 Mbps PS-OTG pair \xE2\x80\x94 safe-direction high (not among the 69 v1 P/N-token pairs; class affects ordering only)"},
        {"FMC_LA05_P", "MODERATE",
         "FMC LVDS user pair (LVDS_25) \xE2\x80\x94 speed set by the mezzanine, budget relaxed vs TMDS"},
        {"LCD_G3", "MODERATE", "LCD parallel RGB data @ ~33 MHz pixel clock, simultaneous-switching bus"},
        {"LCD_CTP_SDA", "LOW", "capacitive-touch-panel I2C + control \xE2\x80\x94 400 kHz class"},
        {"ESC_PWM_IN2", "LOW", "ESC PWM (50-490 Hz class) + buffer control"},
        {"CAM_SCL", "LOW", "camera control / SCCB I2C"},
        {"SDIO_D3", "LOW", "SDIO @ 50 MHz single-ended, short reach, terminated at the SoM"},
        {"ZYNQ_PS_MIO12", "LOW", "PS MIO GPIO / voltage-monitor strap"},
        {"VIN", "LOW",
         "power inlet leaked under a signal-style name (no '+' prefix) \xE2\x80\x94 carried by planes, not lanes"},
    };
    require(expected.size() >= minimum_named_nets, "too few named nets");
    for (const auto& item : expected) {
        const auto found = classify_pcb_escape_signal(item.net, {}, triage);
        require(found.klass == item.klass, std::string(item.net) + " class " + found.klass);
        require(found.basis == item.note, std::string(item.net) + " note " + found.basis);
    }
}

}

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: escape_triage_contracts REPOSITORY");
        const fs::path repository = argv[1];
        const Scratch scratch;
        real_files_load(repository);
        first_match_wins(scratch);
        full_match_only(scratch);
        unmatched_net_has_no_default(scratch);
        function_map_is_applied(scratch);
        rejections(scratch);
        carrier_classification(repository);
        std::cout << "escape triage contracts: " << checks << " checks passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "escape triage contracts failed: " << error.what() << "\n";
        return 1;
    }
}
