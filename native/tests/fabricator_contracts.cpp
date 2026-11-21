#include "schgen/fabricator.hpp"
#include "schgen/run_config.hpp"
#include "schgen/stackup.hpp"

#include <fstream>
#include <iostream>
#include <sstream>

namespace {
using namespace schgen;
std::size_t checks = 0;
void require(bool test, const std::string& why) {
    ++checks;
    if (!test) throw std::runtime_error(why);
}
template <class F> void rejects(F action, const std::string& fragment, const std::string& why) {
    ++checks;
    try { action(); } catch (const std::exception& error) {
        if (std::string(error.what()).find(fragment) != std::string::npos) return;
        throw std::runtime_error(why + ": wrong message: " + error.what());
    }
    throw std::runtime_error(why + ": accepted");
}
std::string read(const std::filesystem::path& file) {
    std::ifstream in(file, std::ios::binary);
    std::stringstream text;
    text << in.rdbuf();
    return text.str();
}
std::string replaced(std::string text, const std::string& from, const std::string& to) {
    const std::size_t at = text.find(from);
    if (at == std::string::npos) throw std::runtime_error("mutation target missing: " + from);
    return text.replace(at, from.size(), to);
}
FabricatorProfile parsed(const std::string& text) { return parse_fabricator(parse_json_text(text), "fabricators/jlcpcb.json"); }

void profile_contracts(const std::filesystem::path& root) {
    const std::string text = read(root / "fabricators/jlcpcb.json");
    const FabricatorProfile profile = load_fabricator(root / "fabricators/jlcpcb.json");
    require(profile.name == "JLCPCB", "profile name");
    require(profile.for_copper(1, fabricator_key::trace) == 0.09 && profile.for_copper(1, fabricator_key::space) == 0.09, "1 oz trace and space");
    require(profile.for_copper(2, fabricator_key::trace) == 0.15, "2 oz trace");
    require(profile.for_copper(1, fabricator_key::mask_bridge) == 0.10 && profile.for_copper(2, fabricator_key::mask_bridge) == 0.20, "mask bridge by copper weight");
    require(profile.number(fabricator_key::silk_height) == 1.0 && profile.number(fabricator_key::silk_line) == 0.15, "silk minima");
    require(profile.number(fabricator_key::hole_via) == 0.2 && profile.number(fabricator_key::hole_pad) == 0.45, "hole to hole by kind");
    require(profile.number(fabricator_key::slot_ratio_min) == 2.0 && profile.number(fabricator_key::slot_width_min) == 0.35, "plated slot rule");
    require(profile.number(fabricator_key::designators_per_line) == 200.0, "designators per BOM line");
    require(profile.texts(fabricator_key::cpl_columns) == std::vector<std::string>({"Designator", "Mid X", "Mid Y", "Layer", "Rotation"}), "CPL columns");
    require(profile.texts(fabricator_key::bom_columns) == std::vector<std::string>({"Comment", "Designator", "Footprint", "JLCPCB Part #"}), "BOM columns");
    for (const auto& [path, value] : profile.values) {
        require(!value.unit.empty(), path + " has a unit");
        require(value.known() ? !value.source_url.empty() && !value.read_utc.empty() && !value.quote.empty() : !value.unverified.empty(), path + " is sourced or explicitly unverified");
    }
    require(!profile.known("assembly.placement_accuracy_mm") && !profile.known("assembly.component_height_max_mm"), "unverified values stay null");
    rejects([&] { profile.number("assembly.placement_accuracy_mm"); }, "UNVERIFIED", "an unverified value was read as a number");
    rejects([&] { profile.at("fab.nothing"); }, "fab.nothing", "an unknown key was read");
    rejects([&] { profile.for_copper(3, fabricator_key::trace); }, "no rules for 3 oz", "an unpublished copper weight was read");
    rejects([&] { parsed(replaced(text, "\"name\": \"JLCPCB\",", "\"name\": \"JLCPCB\", \"surprise\": 1,")); }, "surprise", "unknown top key");
    rejects([&] { parsed(replaced(text, "\"quote\":", "\"quoted\":")); }, "quoted", "unknown or missing quote key");
    rejects([&] { parsed(replaced(text, "\"source_url\":", "\"source\":")); }, "source", "missing source");
    rejects([&] { parsed(replaced(text, "\"unit\": \"mm\"", "\"unit\": \"in\"")); }, "unit 'in' is wrong", "wrong unit");
    rejects([&] { parsed(replaced(text, "\"read_utc\": \"2026-11-21T12:50:07Z\"", "\"read_utc\": \"yesterday\"")); }, "not a UTC time stamp", "bad time stamp");
    rejects([&] { parsed(replaced(text, "\"unverified\":", "\"reason\":")); }, "reason", "null without reason");
    rejects([&] { parsed(replaced(text, "\"npth_min_mm\"", "\"npth_min\"")); }, "npth_min", "renamed key");
    rejects([&] { parsed(replaced(text, "\"value\": 0.09,", "\"value\": \"0.09\",")); }, "wrong type", "text where a number belongs");
    rejects([&] { parsed(replaced(text, "schgen.fabricator/1", "schgen.fabricator/2")); }, "unknown schema", "schema");
    rejects([&] { load_fabricator(root / "fabricators/absent.json"); }, "not found", "missing file");
}

std::string scratch_config(const std::filesystem::path& root, const std::filesystem::path& dir, const std::string& from, const std::string& to) {
    std::filesystem::create_directories(dir);
    const std::string text = from.empty() ? read(root / "schgen.json") : replaced(read(root / "schgen.json"), from, to);
    std::ofstream(dir / "schgen.json", std::ios::binary) << text;
    return (dir / "schgen.json").string();
}

void run_config_contracts(const std::filesystem::path& root) {
    const std::filesystem::path scratch = std::filesystem::temp_directory_path() / "schgen_fabricator_contracts";
    std::filesystem::remove_all(scratch);
    const RunConfig real = load_run_config(root / "schgen.json");
    for (const std::string& board : real.boards) {
        const FabricationConfig& row = real.fabrication_of(board);
        require(row.fabricator == "jlcpcb" && row.finish == "ENIG" && row.assembly_service == "standard" && row.build_count >= 1, board + " fabrication row");
    }
    rejects([&] { real.fabrication_of("absent"); }, "'fabrication' names no entry for board 'absent'", "unknown board");
    rejects([&] { load_run_config(scratch_config(root, scratch / "a", "\"fabrication\": {", "\"fabricationx\": {")); }, "fabricationx", "renamed table");
    rejects([&] { load_run_config(scratch_config(root, scratch / "b", "\"build_count\": 5", "\"build_count\": 5, \"surprise\": 1")); }, "surprise", "unknown key in a board's fabrication");
    rejects([&] { load_run_config(scratch_config(root, scratch / "c", "\"build_count\": 5", "\"build_count\": 0")); }, "build_count", "zero build count");
    rejects([&] { load_run_config(scratch_config(root, scratch / "d", "\"finish\": \"ENIG\"", "\"finish\": 7")); }, "finish", "finish that is not a name");
    rejects([&] { apply_run_config(scratch_config(root, scratch / "e", "\"finish\": \"ENIG\"", "\"finish\": \"HASL\""), real.boards.front()); }, "do not support HASL", "HASL on a six-layer board");
    rejects([&] { apply_run_config(scratch_config(root, scratch / "f", "\"finish\": \"ENIG\"", "\"finish\": \"GOLD\""), real.boards.front()); }, "'GOLD' is not offered", "unknown finish");
    rejects([&] { apply_run_config(scratch_config(root, scratch / "g", "\"outer_oz\": 1", "\"outer_oz\": 3"), real.boards.front()); }, "outer copper 3 oz is not offered", "unoffered copper");
    rejects([&] { apply_run_config(scratch_config(root, scratch / "h", "\"outer_oz\": 1", "\"outer_oz\": 2"), real.boards.front()); }, "the selected stack-up is published for 1 oz outer", "copper that differs from the stack-up");
    rejects([&] { apply_run_config(scratch_config(root, scratch / "i", "\"assembly_service\": \"standard\"", "\"assembly_service\": \"express\""), real.boards.front()); }, "'express' is not in the profile", "unknown service");
    rejects([&] { apply_run_config(scratch_config(root, scratch / "j", "\"fabricator\": \"jlcpcb\"", "\"fabricator\": \"nowhere\""), real.boards.front()); }, "fabricator profile not found", "unknown fabricator");
    apply_run_config(root / "schgen.json", real.boards.front());
    require(board_fabrication().config.outer_oz == 1.0 && board_fabrication().outer_value(fabricator_key::trace) == 0.09, "selection carries the board's copper weight");
    require(board_stackup().outer_oz == 1.0 && board_stackup().inner_oz == 0.5, "stack-ups carry the copper weights they were published for");
    std::filesystem::remove_all(scratch);
}
}

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("repo root required");
        profile_contracts(argv[1]);
        run_config_contracts(argv[1]);
        std::cout << "fabricator: " << checks << " assertions passed\n";
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
