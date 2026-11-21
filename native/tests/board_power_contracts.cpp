#include "schgen/board_power.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {
using namespace schgen;
namespace fs = std::filesystem;

constexpr double input_volts = 20.0, target_volts = 5.0, fixed_volts = 1.8, feedback_vref = 1.0;
constexpr double top_ohms = 40200.0, bottom_ohms = 10000.0, mutated_top_ohms = 33000.0;
std::size_t checks = 0;

void require(bool condition, const std::string& why) { ++checks; if (!condition) throw std::runtime_error(why); }

template <class F> std::string failure(F&& action) {
    try { action(); } catch (const std::exception& e) { return e.what(); }
    return {};
}

BoardPower power_of(const std::string& text) { return parse_board_power(parse_json_text(text, "fixture"), "fixture board"); }

CircuitPartIr part(const std::string& ref, const std::string& lib_id, const std::string& value) {
    CircuitPartIr p;
    p.ref = ref;
    p.lib_id = lib_id;
    p.value = value;
    return p;
}

CircuitNetIr net(const std::string& name, const std::string& klass, std::vector<CircuitPinRefIr> pins) {
    CircuitNetIr n;
    n.name = name;
    n.net_class = klass;
    n.pins = std::move(pins);
    return n;
}

CircuitSheetIr buck_sheet(const std::string& top) {
    CircuitSheetIr c;
    c.name = "buck";
    c.parts = {part("U1", "LM61460AANRJRR:LM61460AANRJRR", "LM61460AANRJRR"), part("L1", "Device:L", "2.2uH"),
               part("R1", "Device:R", top), part("R2", "Device:R", "10k")};
    c.nets = {net("+VIN_T", "power", {{"U1", "8"}}), net("SW_T", "signal", {{"U1", "10"}, {"L1", "1"}}),
              net("+VOUT_T", "power", {{"L1", "2"}, {"R1", "1"}}), net("FB_T", "signal", {{"U1", "4"}, {"R1", "2"}, {"R2", "1"}}),
              net("GND", "ground", {{"R2", "2"}})};
    return c;
}

void loader() {
    const std::string good = R"({"sources": [{"rail": "+VIN_T", "volts": 20, "amps": 3, "basis": "bench supply"}],
        "rails": [{"rail": "+VOUT_T", "volts": 5, "basis": "target"}, {"rail": "+DARK", "volts": null, "basis": "unpowered by design"}],
        "inlet": null})";
    const auto power = power_of(good);
    require(power.sources.size() == 1 && power.rails.size() == 2 && !power.inlet && !power.rails[1].volts, "power section parses");
    require(failure([] { power_of(R"({"sources": [], "rails": [], "inlet": null, "extra": 1})"); }).find("extra") != std::string::npos, "unknown power key rejected");
    require(failure([] { power_of(R"({"sources": [{"rail": "+A", "volts": 5, "amps": 1}], "rails": [], "inlet": null})"); }).find("basis") != std::string::npos, "source without basis rejected");
    require(failure([] { power_of(R"({"sources": [], "rails": [{"rail": "+A", "volts": 5}], "inlet": null})"); }).find("basis") != std::string::npos, "rail without basis rejected");
    require(failure([] { power_of(R"({"sources": [], "rails": [{"rail": "+A", "basis": "x"}], "inlet": null})"); }).find("volts") != std::string::npos, "rail without volts rejected");
    require(failure([] { power_of(R"({"sources": [], "rails": []})"); }).find("inlet") != std::string::npos, "missing inlet rejected");
    require(failure([] { power_of(R"({"sources": [{"rail": "+A", "supplier": "module", "volts": 3}], "rails": [], "inlet": null})"); }).find("volts") != std::string::npos, "module-supplied source states no values");
    require(failure([] { power_of(R"({"sources": [], "rails": [{"rail": "+A", "volts": 1, "basis": "x"}, {"rail": "+A", "volts": 1, "basis": "y"}], "inlet": null})"); }).find("twice") != std::string::npos, "rail listed twice rejected");
}

void module_keys(const fs::path& root) {
    auto document = parse_json_file((root / "som/module.json").string());
    const auto module = parse_module(document, "module");
    require(module.supplies.size() == 1 && !module.regulated_rails.empty() && !module.regulated_rails_basis.empty(), "module power keys parse");
    auto without_basis = document;
    for (auto& [key, value] : without_basis.object_value)
        if (key == "supplies") value.array_value.front().object_value.pop_back();
    require(failure([&] { parse_module(without_basis, "module"); }).find("basis") != std::string::npos, "module supply without basis rejected");
    auto unknown = document;
    for (auto& [key, value] : unknown.object_value)
        if (key == "supplies") value.array_value.front().object_value.emplace_back("connector", parse_json_text("\"J1\""));
    require(failure([&] { parse_module(unknown, "module"); }).find("connector") != std::string::npos, "unknown module supply key rejected");
    auto board = parse_json_file((root / "carrier/board.json").string());
    auto no_power = board;
    no_power.object_value.erase(std::remove_if(no_power.object_value.begin(), no_power.object_value.end(), [](const auto& kv) { return kv.first == "power"; }), no_power.object_value.end());
    require(failure([&] { parse_board(no_power, "board", module); }).find("power") != std::string::npos, "board without power rejected");
}

void derivation() {
    const auto& facts = default_part_facts();
    const ModuleDefinition module;
    const std::vector<ProjectCircuit> buck{{"buck", {}, buck_sheet("40k2")}};
    const auto source = power_of(R"({"sources": [{"rail": "+VIN_T", "volts": 20, "amps": 3, "basis": "bench"}], "rails": [], "inlet": null})");
    const auto missing = failure([&] { board_power_policy(source, module, {}, {}, buck, facts); });
    require(missing.find("+VOUT_T") != std::string::npos && missing.find("5.02") != std::string::npos, "adjustable output without a target fails naming the rail and its divider value: " + missing);
    const auto stated = power_of(R"({"sources": [{"rail": "+VIN_T", "volts": 20, "amps": 3, "basis": "bench"}], "rails": [{"rail": "+VOUT_T", "volts": 5, "basis": "target"}], "inlet": null})");
    const auto policy = board_power_policy(stated, module, {}, {}, buck, facts);
    require(rail_volts("+VOUT_T", policy) == target_volts && rail_volts("+VIN_T", policy) == input_volts, "target and source voltages");

    const auto base = feedback_divider(buck.front().circuit, "U1", "+VOUT_T", feedback_vref);
    require(base && base->volts == feedback_vref * (1 + top_ohms / bottom_ohms) && base->top_ref == "R1" && base->bottom_ref == "R2", "divider follows its resistors");
    const auto mutated = feedback_divider(buck_sheet("33k"), "U1", "+VOUT_T", feedback_vref);
    require(mutated && mutated->volts == feedback_vref * (1 + mutated_top_ohms / bottom_ohms) && mutated->volts < base->volts, "mutated top resistor moves the set point by the formula");

    CircuitSheetIr lonely;
    lonely.name = "lonely";
    lonely.parts = {part("R1", "Device:R", "1k")};
    lonely.nets = {net("+ORPHAN_T", "power", {{"R1", "1"}}), net("GND", "ground", {{"R1", "2"}})};
    const auto empty = power_of(R"({"sources": [], "rails": [], "inlet": null})");
    const auto orphan = failure([&] { board_power_policy(empty, module, {}, {}, {{"lonely", {}, lonely}}, facts); });
    require(orphan.find("+ORPHAN_T") != std::string::npos, "power-class net with no home fails naming the net: " + orphan);
    const auto dark = board_power_policy(power_of(R"({"sources": [], "rails": [{"rail": "+ORPHAN_T", "volts": null, "basis": "unpowered"}], "inlet": null})"), module, {}, {}, {{"lonely", {}, lonely}}, facts);
    require(!rail_volts("+ORPHAN_T", dark) && dark.rails.size() == 1, "explicit null is a stated home");
    require(failure([&] { board_power_policy(power_of(R"({"sources": [], "rails": [{"rail": "+NOT_ON_BOARD", "volts": 1, "basis": "x"}], "inlet": null})"), module, {}, {}, {{"lonely", {}, lonely}}, facts); }).find("+NOT_ON_BOARD") != std::string::npos, "stale entry fails");

    CircuitSheetIr ldo;
    ldo.name = "ldo";
    ldo.parts = {part("U1", "AP2112K-1.8TRG1:AP2112K-1.8TRG1", "AP2112K-1.8"), part("R9", "Device:R", "0R")};
    ldo.nets = {net("+IN_T", "power", {{"U1", "1"}}), net("+OUT_T", "power", {{"U1", "5"}, {"R9", "1"}}), net("+LINK_T", "power", {{"R9", "2"}}), net("GND", "ground", {{"U1", "2"}})};
    const std::vector<ProjectCircuit> ldo_sheets{{"ldo", {}, ldo}};
    const auto fed = power_of(R"({"sources": [{"rail": "+IN_T", "volts": 3.3, "amps": 1, "basis": "bench"}], "rails": [], "inlet": null})");
    const auto fixed = board_power_policy(fed, module, {}, {}, ldo_sheets, facts);
    require(rail_volts("+OUT_T", fixed) == fixed_volts && rail_volts("+LINK_T", fixed) == fixed_volts, "fixed output and its 0R bridge carry the part's out_v");
    const auto twice = failure([&] { board_power_policy(power_of(R"({"sources": [{"rail": "+IN_T", "volts": 3.3, "amps": 1, "basis": "bench"}], "rails": [{"rail": "+OUT_T", "volts": 1.8, "basis": "dup"}], "inlet": null})"), module, {}, {}, ldo_sheets, facts); });
    require(twice.find("+OUT_T") != std::string::npos && twice.find("two homes") != std::string::npos, "an entry for a derivable rail is a second home: " + twice);
    const auto clash = failure([&] { board_power_policy(power_of(R"({"sources": [{"rail": "+IN_T", "volts": 3.3, "amps": 1, "basis": "bench"}], "rails": [{"rail": "+LINK_T", "volts": 2.5, "basis": "wrong"}], "inlet": null})"), module, {}, {}, ldo_sheets, facts); });
    require(clash.find("+LINK_T") != std::string::npos, "a bridge between two different voltages fails: " + clash);
}
}

int main(int argc, char** argv) {
    try {
        const fs::path root = argc > 1 ? argv[1] : fs::current_path();
        loader();
        module_keys(root);
        derivation();
        std::cout << checks << " board power contracts passed\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "board_power_contracts FAILED after " << checks << ": " << e.what() << '\n';
        return 1;
    }
}
