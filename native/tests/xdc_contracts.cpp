// The golden text and rejection messages were checked against the Python XDC
// implementation at 00432da5. This executable has no Python/runtime dependency.
#include "schgen/xdc.hpp"

#include <fstream>
#include <cmath>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

schgen::XdcInput corpus() {
    schgen::XdcInput in;
    in.connectors = {
        {"J1", {{"10", "IO_SINGLE"}, {"2", "IO_N"}, {"1", "IO_P"},
                {"3", "GND"}, {"4", "VIN"}, {"5", "unconnected-1"}, {"6", "PS_MIO"}}},
        {"J2", {{"2", "IO_TMDS_N"}, {"1", "IO_TMDS_P"}, {"3", "IO_GPIO"}, {"4", "AUX"}}}};
    in.ball_net = {{"C1", "IO_SINGLE"}, {"B2", "IO_N"}, {"B1", "IO_P"},
                   {"D2", "IO_TMDS_N"}, {"D1", "IO_TMDS_P"}, {"A10", "IO_GPIO"},
                   {"E1", "AUX"}, {"F1", "PS_MIO"}};
    in.pin_names = {{"C1", "IO_L2N_MRCC_34"}, {"B2", "IO_L1N_T0_34"},
                    {"B1", "IO_L1P_T0_MRCC_34"}, {"D2", "IO_L1N_T0_35"},
                    {"D1", "IO_L1P_T0_35"}, {"A10", "IO_L2P_SRCC_13"},
                    {"E1", "IO_1_35"}, {"F1", "PS_MIO1_500"}};
    for (const auto& [ref, pins] : in.connectors)
        for (const auto& [pin, net] : pins) in.jpin_net.emplace_back(ref + "." + pin, net);
    in.function_map = {{"IO_SINGLE", "STATUS"}, {"IO_P", "DATA_P"}, {"IO_N", "DATA_N"},
                       {"IO_TMDS_P", "HDMI_P"}, {"IO_TMDS_N", "HDMI_N"}, {"AUX", "RESET"}};
    in.bank_rails = in.vcco_rails = {{"34", "+2V5"}, {"35", "+3V3"}, {"13", "+1V8"}};
    for (const auto* net : {"STATUS", "DATA_N", "DATA_P", "HDMI_N", "HDMI_P", "IO_GPIO", "RESET"})
        in.ports.push_back({net, "som_j1", "single", std::nullopt, std::nullopt, -1});
    in.ports.push_back({"DATA_P", "lvds", "diff_pair", "DATA_N", 100, 0});
    in.ports.push_back({"DATA_N", "lvds", "diff_pair", "DATA_P", 100, 1});
    in.ports.push_back({"HDMI_N", "video", "tmds_pair", "HDMI_P", 100, 2});
    in.ports.push_back({"HDMI_P", "video", "tmds_pair", "HDMI_N", 100, 3});
    in.ports.push_back({"STATUS", "monitor", "single", std::nullopt, std::nullopt, 4});
    in.ports.push_back({"STATUS", "debug", "single", std::nullopt, std::nullopt, 5});
    in.ports.push_back({"DATA_P", "observer", "diff_pair", "missing", 90, 6});
    in.refs = {"J1", "J2"};
    in.device = "XC7Z020-CLG400";
    in.zynq_ref = "U2";
    in.contract_path = in.contract_source = "carrier/som_interface.json";
    in.som_source = "som/Zynq_SoM.kicad_sch";
    return in;
}

template<class F>
void rejects(F mutation, const std::string& expected) {
    auto in = corpus();
    mutation(in);
    try {
        schgen::generate_xdc(in);
    } catch (const schgen::XdcError& e) {
        require(e.what() == expected, "diagnostic changed: " + std::string(e.what()));
        return;
    }
    throw std::runtime_error("invalid XDC inputs were accepted: " + expected);
}

void checks(const char* golden_path) {
    std::ifstream golden(golden_path, std::ios::binary);
    require(golden.good(), "cannot read XDC golden fixture");
    const std::string expected((std::istreambuf_iterator<char>(golden)), {});
    const auto out = schgen::generate_xdc(corpus());
    require(out.text == expected, "native XDC bytes differ from Python baseline");
    require(out.entries.size() == 7, "pin population changed");
    require(out.entries[0].net == "DATA_P" && out.entries[1].net == "DATA_N" &&
            out.entries[2].jpin == "J1.10", "numeric connector ordering changed");
    require(out.entries[0].type.type_index == 0, "first non-single port type was overwritten");
    require(out.entries[0].consumers == std::vector<std::string>{"lvds", "observer"},
            "consumer order/filter changed");
    require(out.checks == std::vector<std::string>{
        "J1: all 7 contract pins match the live SoM netlist verbatim",
        "J2: all 4 contract pins match the live SoM netlist verbatim",
        "emitted pin count 7 == live J1/J2-to-PL net population 7",
        "7 unique balls, 7 unique ports (no double-claims)",
        "7 set_property lines for 7 pins"}, "validation evidence changed");
    require(schgen::xdc_pin_traits("IO_L12P_SRCC_MRCC_34") ==
            std::make_pair(std::string("MRCC"), true), "clock priority/polarity changed");
    require(schgen::xdc_rail_volts("+2V5_AUX") == 2.5, "rail suffix handling changed");
    require(schgen::xdc_rail_volts("+5V") == 5.0, "integer voltage changed");

    rejects([](auto& in) { in.vcco_rails[0].second = "+3V3"; },
        "VCCO bank-rail drift: project.json fpga.bank_rails and the "
        "project som_conn_gen.VCCO_RAIL_MAP disagree — the XDC would emit "
        "the wrong IOSTANDARD on a re-railed bank: "
        "{'34': {'bank_rails': '+2V5', 'VCCO_RAIL_MAP': '+3V3'}}");
    rejects([](auto& in) { in.refs = {"J9"}; }, "J9 missing from carrier/som_interface.json");
    rejects([](auto& in) { in.jpin_net.pop_back(); },
        "J2: contract pin set != live SoM netlist — som_interface.json is STALE; "
        "re-run `schgen som-interface`");
    rejects([](auto& in) { in.jpin_net[0].second = "wrong'net"; },
        "J1.10: contract says 'IO_SINGLE' but the SoM netlist says \"wrong'net\" — "
        "som_interface.json is STALE; re-run `schgen som-interface`");
    rejects([](auto& in) {
        in.ball_net.emplace_back("A1", "IO_P");
        in.pin_names.emplace_back("A1", "IO_1_34");
    }, "'IO_P': reaches 2 PL balls (['A1', 'B1']) — ambiguous LOC, refusing to guess");
    rejects([](auto& in) { in.ports.clear(); },
        "orphan: J1.1 net 'IO_P' reaches PL ball B1 but is not a PORT on any carrier sheet");
    rejects([](auto& in) {
        in.function_map.emplace_back("IO_GPIO", "unsafe-name");
        in.ports.push_back({"unsafe-name", "test", "single", std::nullopt, std::nullopt, -1});
    }, "'unsafe-name': not a safe Vivado port name (get_ports needs [A-Za-z0-9_]+)");
    rejects([](auto& in) { in.pin_names[2].second = "IO_L1P"; },
        "ball B1 pin name 'IO_L1P' carries no bank suffix");
    rejects([](auto& in) {
        in.connectors[0].second.emplace_back("11", "IO_P");
        in.jpin_net.emplace_back("J1.11", "IO_P");
    }, "ball B1 claimed twice: 'DATA_P' and 'DATA_P'");
    rejects([](auto& in) { in.function_map[2].second = "DATA_P"; },
        "net 'DATA_P' mapped twice: J1.1 and J1.2");
    rejects([](auto& in) { in.ball_net.clear(); },
        "no carrier port reaches a PL ball through J1/J2 — wrong refs?");
    rejects([](auto& in) {
        in.bank_rails.erase(in.bank_rails.begin()); in.vcco_rails = in.bank_rails;
    }, "bank 34 (DATA_P @ B1): no VCCO rail decision in project.json fpga.bank_rails — "
       "decide the rail there, never default");
    rejects([](auto& in) { in.ports[7].pair_with = "missing"; },
        "DATA_P: typed diff_pair but its complement 'missing' is not bound through "
        "J1/J2 — half a pair cannot be constrained");
    rejects([](auto& in) {
        in.bank_rails[0].second = "+3V3"; in.vcco_rails = in.bank_rails;
    }, "DATA_P: LVDS_25 needs a 2.5 V bank, bank 34 runs +3V3 (bank 34)");
    rejects([](auto& in) {
        in.bank_rails[1].second = "+2V5"; in.vcco_rails = in.bank_rails;
    }, "HDMI_P: TMDS_33 needs a 3.3 V bank, bank 35 runs +2V5");
    rejects([](auto& in) {
        in.bank_rails[2].second = "+1V2"; in.vcco_rails = in.bank_rails;
    }, "bank 13: no LVCMOS standard for 1.2 V rail +1V2");
    rejects([](auto& in) { in.function_map.emplace_back("IO_GPIO", "+1V8"); },
        "emitted 6 pins but the live netlist shows 7 J1/J2 nets on PL balls — a net was dropped");
    rejects([](auto& in) { in.ports[8].pair_with = "DATA_N"; },
        "wrote 9 set_property lines for 7 pins — renderer bug");

    for (const auto& [rail, value] : schgen::XdcStrings{
            {"+5V", "5.0"}, {"+0V00001", "1e-05"}, {"+0V0001", "0.0001"},
            {"+1V2345678901234567", "1.2345678901234567"},
            {"+10000000000000000V", "1e+16"}, {"+" + std::string(400, '9') + "V", "inf"}}) {
        rejects([voltage_rail = rail](auto& in) {
            in.bank_rails[2].second = voltage_rail; in.vcco_rails = in.bank_rails;
        }, "bank 13: no LVCMOS standard for " + value + " V rail " + rail);
    }
    for (const auto* rail : {"3V3", "GND", "+VIN"}) {
        bool rejected = false;
        try { schgen::xdc_rail_volts(rail); }
        catch (const schgen::XdcError& e) {
            require(std::string(e.what()) == std::string("cannot parse voltage from rail name '") +
                    rail + "'", "malformed rail diagnostic changed");
            rejected = true;
        }
        require(rejected, "invalid voltage rail accepted");
    }
    require(schgen::xdc_rail_volts("+0V" + std::string(400, '0') + "1") == 0.0,
            "rail decimal underflow changed");
    require(std::isinf(schgen::xdc_rail_volts("+" + std::string(400, '9') + "V")),
            "rail decimal overflow changed");

    auto usb = corpus();
    for (auto& port : usb.ports) {
        if (port.kind == "diff_pair") port.kind = "usb_hs_pair";
        port.impedance.reset();
    }
    const auto usb_out = schgen::generate_xdc(usb);
    require(usb_out.text.find("# usb_hs_pair (NoneR): DATA_P / DATA_N\n") != std::string::npos,
            "USB pair kind / absent impedance changed");
    require(usb_out.entries[0].iostd == "LVDS_25", "USB pair standard changed");

    auto numbers = corpus();
    const auto rename_pin = [](auto& in, const std::string& before, const std::string& after) {
        for (auto& [pin, net] : in.connectors[0].second) if (pin == before) pin = after;
        for (auto& [jp, net] : in.jpin_net) if (jp == "J1." + before) jp = "J1." + after;
    };
    rename_pin(numbers, "1", "100000000000000000000000000000");
    rename_pin(numbers, "2", "-2");
    rename_pin(numbers, "10", "02");
    const auto numbered = schgen::generate_xdc(numbers);
    require(numbered.entries[0].net == "DATA_N" && numbered.entries[1].net == "STATUS" &&
            numbered.entries[2].net == "DATA_P", "large/signed numeric pin ordering changed");
    numbers = corpus();
    rename_pin(numbers, "10", "01");
    const auto tied = schgen::generate_xdc(numbers);
    require(tied.entries[0].net == "STATUS" && tied.entries[1].net == "DATA_P",
            "equal numeric pin IDs lost stable input ordering");
    rejects([&](auto& in) { rename_pin(in, "10", "1tail"); },
            "invalid literal for int() with base 10: '1tail'");

    // A diagnostic ordering hint must not exempt any bank from validation.
    rejects([](auto& in) {
        in.drift_order = {"13", "13", "unknown"};
        in.vcco_rails[0].second = "+3V3";
    }, "VCCO bank-rail drift: project.json fpga.bank_rails and the "
       "project som_conn_gen.VCCO_RAIL_MAP disagree — the XDC would emit "
       "the wrong IOSTANDARD on a re-railed bank: "
       "{'34': {'bank_rails': '+2V5', 'VCCO_RAIL_MAP': '+3V3'}}");
}
}  // namespace

int main(int argc, char** argv) {
    try {
        require(argc == 2, "expected XDC golden fixture path");
        checks(argv[1]);
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
