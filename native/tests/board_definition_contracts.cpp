#include "schgen/board_definition.hpp"
#include "schgen/board_files.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

namespace {

using namespace schgen;

std::size_t checks = 0;

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

std::string replaced(std::string text, const std::string& before, const std::string& after) {
    const auto at = text.find(before);
    if (at == std::string::npos) throw std::runtime_error("fixture lacks " + before);
    return text.replace(at, before.size(), after);
}

const char* const small = R"json({
  "schema": "schgen.board/1",
  "name": "bench",
  "files": {"stem": "Bench_Board"},
  "root_readme": false,
  "owned_groups": ["power"],
  "module": {
    "folder": "bench_module",
    "pairs": [{"positive": "BOARD_P", "negative": "BOARD_N", "kind": "diff_pair", "impedance": 90}],
    "loads": [{"connector": "J2", "rail": "+3V3", "amps": 0.02, "note": "bank supply"}]
  },
  "power": {
    "sources": [{"rail": "+VIN", "volts": 12.0, "amps": 2.0, "basis": "bench supply"}, {"rail": "+3V3_SC", "supplier": "module"}],
    "rails": [{"rail": "+5V", "volts": 5.0, "basis": "buck target"}],
    "inlet": null
  },
  "sheets": [
    {"name": "som_j1", "module_connector": "J1", "title": "Module connector one"},
    {"name": "power", "settings": {"bind": {"+VIN": "+VIN_SYS"}}, "additions": {"draws": []}},
    {"name": "mechanical"}
  ]
})json";

const char* const small_module = R"json({
  "schema": "schgen.module/1",
  "schematic": "Bench_Module.kicad_sch",
  "pcb": "Bench_Module.kicad_pcb",
  "connector_part": "DF40C-100DP-0.4V_51",
  "controller_ref": "U9",
  "fpga_ref": "U2",
  "draw": {"connector": "J1", "rail": "VIN", "amps": 2.15, "note": "module supply"},
  "sdio_level_v": 1.8,
  "sd_bus": ["SDIO_CLK", "SDIO_CMD"],
  "pairs": [{"positive": "USB_P", "negative": "USB_N", "kind": "usb_hs_pair"},
            {"positive": "ETH_P", "negative": "ETH_N", "kind": "diff_pair", "impedance": 100}],
  "escape_population": {
    "netted_contacts": {"J1": 93, "J2": 100},
    "return_path": {"n_pairs": 69, "n_pair_contacts": 138, "n_fail": 29, "worst_distance": 4}
  },
  "escape_triage": [{"pattern": "USB_.*", "class": "GENUINE", "note": "pair"}],
  "do_not_load_straps": ["MIO7"],
  "supplies": [{"rail": "+3V3_SC", "volts": 3.3, "amps": 0.3, "basis": "module always-on LDO"}],
  "regulated_rails": {"rails": ["+1V8"], "basis": "module-regulated rail"}
})json";

BoardDefinition parsed(const std::string& text) {
    return parse_board(parse_json_text(text), "fixture", parse_module(parse_json_text(small_module), "fixture module"));
}

ModuleDefinition module_parsed(const std::string& text) { return parse_module(parse_json_text(text), "fixture module"); }

struct Scratch {
    std::filesystem::path root;
    Scratch() : root(std::filesystem::temp_directory_path() / "schgen_board_definition_contracts") {
        std::filesystem::remove_all(root);
        std::filesystem::create_directories(root / "bench");
        std::filesystem::create_directories(root / "bench_module");
    }
    ~Scratch() { std::filesystem::remove_all(root); }
    void put(const std::string& relative, const std::string& text) const {
        std::ofstream(root / relative, std::ios::binary) << text;
    }
};

void reads_a_board() {
    const BoardDefinition board = parsed(small);
    require(board.name == "bench" && board.sheets.size() == 3, "the sheets are listed in file order");
    require(board.files.stem == "Bench_Board", "the file stem is read from files.stem");
    require(!board.flags.root_readme && board.flags.owned_groups == std::vector<std::string>{"power"}, "the document and placement flags are read");
    require(board.sheet("som_j1").from_module() && board.sheet("som_j1").module_connector == "J1", "a module connector sheet names its connector");
    require(!board.sheet("power").from_module() && board.sheet("power").additions.has_value(), "a library sheet carries its settings and additions");
    require(board.sheet("mechanical").settings.kind == JsonKind::Object && board.sheet("mechanical").settings.object_value.empty(),
            "a sheet with no settings has an empty settings object");
    require(board.module.folder == "bench_module", "the module folder is named by the board");
    require(board.module.pairs.size() == 1 && board.module.pairs.front().impedance == 90 && board.module.loads.front().connector == "J2",
            "board pairs and loads are read");
    require(board.module_definition.draw.rail == "VIN" && board.module_definition.pairs.size() == 2 && !board.module_definition.pairs.front().impedance &&
                board.module_definition.pairs.back().impedance,
            "module draw is read and pair impedance is optional and kept when given");
    rejects([&] { board.sheet("absent"); }, "has no sheet absent");
}

void names_board_files() {
    require(board_file_name("Bench_Board", BoardFileKind::Schematic) == "Bench_Board.kicad_sch", "schematic name");
    require(board_file_name("Bench_Board", BoardFileKind::Project) == "Bench_Board.kicad_pro", "project name");
    require(board_file_name("Bench_Board", BoardFileKind::Pcb) == "Bench_Board.kicad_pcb", "board name");
    require(board_file_name("Bench_Board", BoardFileKind::DesignRules) == "Bench_Board_pcb.kicad_dru", "design rules name");
    require(board_file_name("Bench_Board", BoardFileKind::Placements) == "Bench_Board_cpl.csv", "placements name");
    require(board_file_name("Bench_Board", BoardFileKind::PlacementsScratch) == "Bench_Board_cpl.pipeline.csv", "placements scratch name");
    require(board_file_name("Bench_Board", BoardFileKind::PinConstraints) == "Bench_Board_pins.xdc", "pin constraints name");
    rejects([] { board_file_name("", BoardFileKind::Pcb); }, "files.stem");
}

void refuses_bad_boards() {
    rejects([] { parsed(replaced(small, "schgen.board/1", "schgen.board/0")); }, "schema is not");
    rejects([] { parsed(replaced(small, "\"name\": \"mechanical\"", "\"name\": \"power\"")); }, "listed twice");
    rejects([] { parsed(replaced(small, "\"amps\": 0.02", "\"amps\": 0")); }, "not above zero");
    rejects([] { parsed(replaced(small, "\"folder\": \"bench_module\"", "\"folder\": \"\"")); }, "field 'folder' is empty");
    rejects([] { parsed(replaced(small, "\"folder\": \"bench_module\"", "\"folder\": \"a/b\"")); }, "not a single folder or file name");
    rejects([] { parsed(replaced(small, "\"folder\": \"bench_module\"", "\"folder\": \"..\"")); }, "not a single folder or file name");
    rejects([] { parsed(replaced(small, "    \"folder\": \"bench_module\",\n", "")); }, "field 'folder' is missing");
    rejects([] { parsed(replaced(small, "    \"folder\": \"bench_module\",\n", "    \"folder\": \"bench_module\", \"draw\": {},\n")); }, "unknown key 'draw'");
    rejects([] { parsed(replaced(small, ",\n    \"loads\": [{\"connector\": \"J2\", \"rail\": \"+3V3\", \"amps\": 0.02, \"note\": \"bank supply\"}]", "")); }, "field 'loads' is missing");
    rejects([] { parsed(replaced(small, "{\"name\": \"mechanical\"}", "{\"name\": \"mechanical\", \"title\": \"x\"}")); },
            "not a module connector sheet");
    rejects([] { parsed(replaced(small, "\"sheets\": [", "\"extra\": 1, \"sheets\": [")); }, "extra");
    rejects([] { parsed(replaced(small, "\"impedance\": 90", "\"impedance\": 90.5")); }, "not a whole number");
    rejects([] { parsed(replaced(small, "  \"files\": {\"stem\": \"Bench_Board\"},\n", "")); }, "field 'files' is missing");
    rejects([] { parsed(replaced(small, "\"stem\": \"Bench_Board\"", "\"stem\": \"\"")); }, "field 'stem' is empty");
    rejects([] { parsed(replaced(small, "\"stem\": \"Bench_Board\"", "\"stem\": \"a/b\"")); }, "holds a path separator");
    rejects([] { parsed(replaced(small, "\"stem\": \"Bench_Board\"", "\"stem\": \"a\\\\b\"")); }, "holds a path separator");
    rejects([] { parsed(replaced(small, "\"stem\": \"Bench_Board\"", "\"stem\": \"Bench_Board\", \"suffix\": \"x\"")); }, "suffix");
    rejects([] { parsed(replaced(small, "\"stem\": \"Bench_Board\"", "\"stem\": 3")); }, "field 'stem' is missing or has the wrong type");
    rejects([] { parsed(replaced(small, "  \"root_readme\": false,\n", "")); }, "field 'root_readme' is missing");
    rejects([] { parsed(replaced(small, "  \"owned_groups\": [\"power\"],\n", "")); }, "field 'owned_groups' is missing");
    rejects([] { parsed(replaced(small, "\"owned_groups\": [\"power\"]", "\"owned_groups\": 1")); }, "field 'owned_groups' is missing or has the wrong type");
    rejects([] { parsed(replaced(small, "\"owned_groups\": [\"power\"]", "\"owned_groups\": true")); }, "field 'owned_groups' is missing or has the wrong type");
    rejects([] { parsed(replaced(small, "\"owned_groups\": [\"power\"]", "\"owned_groups\": [\"absent\"]")); }, "names sheet absent which the board does not list");
    rejects([] { parsed(replaced(small, "\"owned_groups\": [\"power\"]", "\"owned_groups\": [\"power\", \"power\"]")); }, "lists a sheet twice");
    rejects([] { parsed(replaced(small, "\"owned_groups\": [\"power\"]", "\"owned_groups\": [3]")); }, "holds a value that is not a name");
    require(parsed(replaced(small, "\"owned_groups\": [\"power\"]", "\"owned_groups\": []")).flags.owned_groups.empty(), "an empty owned_groups list is a board with no owned groups");
}

void reads_a_module() {
    const ModuleDefinition module = module_parsed(small_module);
    require(module.schematic == "Bench_Module.kicad_sch" && module.pcb == "Bench_Module.kicad_pcb", "module project files are read");
    require(module.connector_part == "DF40C-100DP-0.4V_51" && module.sdio_level_v == 1.8 && module.sd_bus.size() == 2, "module connector policy is read");
    require(module.controller_ref == "U9" && module.fpga_ref == "U2", "module device references are read");
    require(module.netted_contacts.size() == 2 && module.netted_contacts.at("J2") == 100, "netted contacts are read");
    require(module.return_path.n_pairs == 69 && module.return_path.n_pair_contacts == 138 && module.return_path.n_fail == 29 &&
                module.return_path.worst_distance == 4,
            "return path population is read");
    require(module.escape_triage.size() == 1 && module.escape_triage.front().klass == "GENUINE", "triage rules are read");
    require(module.do_not_load_straps.size() == 1 && module.do_not_load_straps.front() == "MIO7", "boot straps are read");
}

void refuses_bad_modules() {
    rejects([] { module_parsed(replaced(small_module, "schgen.module/1", "schgen.module/0")); }, "schema is not");
    rejects([] { module_parsed(replaced(small_module, "  \"schema\": \"schgen.module/1\",\n", "")); }, "field 'schema' is missing");
    rejects([] { module_parsed(replaced(small_module, "  \"schema\": \"schgen.module/1\",", "  \"schema\": \"schgen.module/1\", \"extra\": 1,")); }, "extra");
    rejects([] { module_parsed("[]"); }, "the document is not an object");
    rejects([] { module_parsed(replaced(small_module, "  \"schematic\": \"Bench_Module.kicad_sch\",\n", "")); }, "field 'schematic' is missing");
    rejects([] { module_parsed(replaced(small_module, "  \"pcb\": \"Bench_Module.kicad_pcb\",\n", "")); }, "field 'pcb' is missing");
    rejects([] { module_parsed(replaced(small_module, "\"Bench_Module.kicad_pcb\"", "\"x/Bench_Module.kicad_pcb\"")); }, "not a single folder or file name");
    rejects([] { module_parsed(replaced(small_module, "  \"connector_part\": \"DF40C-100DP-0.4V_51\",\n", "")); }, "field 'connector_part' is missing");
    rejects([] { module_parsed(replaced(small_module, "  \"controller_ref\": \"U9\",\n", "")); }, "field 'controller_ref' is missing");
    rejects([] { module_parsed(replaced(small_module, "  \"fpga_ref\": \"U2\",\n", "")); }, "field 'fpga_ref' is missing");
    rejects([] { module_parsed(replaced(small_module, "\"controller_ref\": \"U9\"", "\"controller_ref\": \"\"")); }, "field 'controller_ref' is empty");
    rejects([] { module_parsed(replaced(small_module, "\"fpga_ref\": \"U2\"", "\"fpga_ref\": 2")); }, "field 'fpga_ref' is missing or has the wrong type");
    rejects([] { module_parsed(replaced(small_module, "\"fpga_ref\": \"U2\"", "\"fpga_ref\": \"U9\"")); }, "name the same reference");
    rejects([] { module_parsed(replaced(small_module, "  \"draw\": {\"connector\": \"J1\", \"rail\": \"VIN\", \"amps\": 2.15, \"note\": \"module supply\"},\n", "")); }, "field 'draw' is missing");
    rejects([] { module_parsed(replaced(small_module, "\"amps\": 2.15", "\"amps\": 0")); }, "not above zero");
    rejects([] { module_parsed(replaced(small_module, "  \"sdio_level_v\": 1.8,\n", "")); }, "field 'sdio_level_v' is missing");
    rejects([] { module_parsed(replaced(small_module, "  \"sd_bus\": [\"SDIO_CLK\", \"SDIO_CMD\"],\n", "")); }, "field 'sd_bus' is missing");
    rejects([] { module_parsed(replaced(small_module, "\"impedance\": 100", "\"impedance\": 100.5")); }, "not a whole number");
    const std::string population_block =
        "  \"escape_population\": {\n    \"netted_contacts\": {\"J1\": 93, \"J2\": 100},\n    \"return_path\": {\"n_pairs\": 69, \"n_pair_contacts\": 138, \"n_fail\": 29, \"worst_distance\": 4}\n  },\n";
    rejects([&] { module_parsed(replaced(small_module, population_block, "")); }, "field 'escape_population' is missing");
    rejects([&] { module_parsed(replaced(small_module, population_block, "  \"escape_population\": {\"x\": 1},\n")); }, "unknown key 'x'");
    rejects([] { module_parsed(replaced(small_module, "    \"netted_contacts\": {\"J1\": 93, \"J2\": 100},\n", "")); }, "field 'netted_contacts' is missing");
    rejects([] { module_parsed(replaced(small_module, "\"netted_contacts\": {\"J1\": 93, \"J2\": 100}", "\"netted_contacts\": {}")); }, "netted_contacts is empty");
    rejects([] { module_parsed(replaced(small_module, "\"J1\": 93", "\"J1\": -1")); }, "netted_contacts.J1 is not a whole number");
    rejects([] { module_parsed(replaced(small_module, "\"J1\": 93", "\"J1\": 93.5")); }, "netted_contacts.J1 is not a whole number");
    rejects([] { module_parsed(replaced(small_module, ",\n    \"return_path\": {\"n_pairs\": 69, \"n_pair_contacts\": 138, \"n_fail\": 29, \"worst_distance\": 4}", "")); }, "field 'return_path' is missing");
    rejects([] { module_parsed(replaced(small_module, "\"n_pairs\": 69, ", "")); }, "field 'n_pairs' is missing");
    rejects([] { module_parsed(replaced(small_module, "\"n_pair_contacts\": 138, ", "")); }, "field 'n_pair_contacts' is missing");
    rejects([] { module_parsed(replaced(small_module, "\"n_fail\": 29, ", "")); }, "field 'n_fail' is missing");
    rejects([] { module_parsed(replaced(small_module, ", \"worst_distance\": 4", "")); }, "field 'worst_distance' is missing");
    rejects([] { module_parsed(replaced(small_module, "\"n_fail\": 29", "\"n_fail\": -1")); }, "field 'n_fail' is not a whole number");
    rejects([] { module_parsed(replaced(small_module, "\"n_fail\": 29", "\"n_fail\": 29, \"extra\": 1")); }, "extra");
    rejects([] { module_parsed(replaced(small_module, "\"escape_triage\": [{\"pattern\": \"USB_.*\", \"class\": \"GENUINE\", \"note\": \"pair\"}],", "")); }, "field 'escape_triage' is missing");
    rejects([] { module_parsed(replaced(small_module, "[{\"pattern\": \"USB_.*\", \"class\": \"GENUINE\", \"note\": \"pair\"}]", "[]")); }, "field 'escape_triage' is empty");
    rejects([] { module_parsed(replaced(small_module, "\"note\": \"pair\"}", "\"note\": \"pair\", \"extra\": 1}")); }, "extra");
    rejects([] { module_parsed(replaced(small_module, "\"pattern\": \"USB_.*\", ", "")); }, "missing");
    rejects([] { module_parsed(replaced(small_module, "\"do_not_load_straps\": [\"MIO7\"]", "\"do_not_load_straps\": [\"\"]")); }, "not a name");
    rejects([] { module_parsed(replaced(small_module, ",\n  \"do_not_load_straps\": [\"MIO7\"]", "")); }, "field 'do_not_load_straps' is missing");
    rejects([] { module_parsed(replaced(small_module, ", \"basis\": \"module always-on LDO\"", "")); }, "field 'basis' is missing");
    rejects([] { module_parsed(replaced(small_module, "\"amps\": 0.3, ", "\"amps\": 0.3, \"connector\": \"J1\", ")); }, "connector");
    rejects([] { module_parsed(replaced(small_module, ", \"basis\": \"module-regulated rail\"", "")); }, "field 'basis' is missing");
    rejects([] { parsed(replaced(small, ", \"basis\": \"bench supply\"", "")); }, "field 'basis' is missing");
    rejects([] { parsed(replaced(small, ", \"basis\": \"buck target\"", "")); }, "field 'basis' is missing");
    rejects([] { parsed(replaced(small, "\"inlet\": null", "\"inlet\": null, \"extra\": 1")); }, "extra");
    rejects([] { parsed(replaced(small, "\"supplier\": \"module\"", "\"supplier\": \"board\"")); }, "supplier");
    {
        const auto board = parsed(small);
        require(board.power.sources.size() == 2 && board.power.sources[1].from_module && board.power.rails.size() == 1 && !board.power.inlet, "board power is read");
    }
}

void loads_a_module_folder() {
    const Scratch scratch;
    const std::string board_text = small;
    rejects([&] { load_board(scratch.root / "bench"); }, "is missing");
    scratch.put("bench/board.json", replaced(board_text, "\"name\": \"bench\"", "\"name\": \"bench\""));
    rejects([&] { load_board(scratch.root / "bench"); }, "bench_module/module.json is missing");
    rejects([&] { load_board_module(scratch.root / "bench"); }, "bench_module/module.json is missing");
    scratch.put("bench_module/module.json", small_module);
    const BoardDefinition board = load_board(scratch.root / "bench");
    require(board.module_definition.connector_part == "DF40C-100DP-0.4V_51" && board.module.folder == "bench_module",
            "a board reads the module file from the folder it names");
    require(module_root_of(scratch.root / "bench") == scratch.root / "bench_module", "the module folder sits beside the board folder");
    require(module_root_in(scratch.root, scratch.root / "bench") == scratch.root / "bench_module", "the module folder is found from the repository root");
    require(load_board_header(scratch.root / "bench").module_folder == "bench_module", "the header names the module folder");
    scratch.put("bench_module/module.json", replaced(small_module, "\"pcb\"", "\"unknown\": 1, \"pcb\""));
    rejects([&] { load_board(scratch.root / "bench"); }, "unknown key 'unknown'");
    rejects([&] { load_board(scratch.root / "bench"); }, "module.json");
    std::filesystem::remove(scratch.root / "bench_module/module.json");
    std::filesystem::remove_all(scratch.root / "bench_module");
    rejects([&] { load_board(scratch.root / "bench"); }, "bench_module/module.json is missing");
}

void reads_the_real_boards(const std::filesystem::path& repository) {
    for (const char* name : {"carrier", "devkit_mini"}) {
        const BoardDefinition board = load_board(repository / name);
        require(board.name == name && !board.sheets.empty(), std::string(name) + " loads from its own folder");
        require(!board.files.stem.empty() && load_board_header(repository / name).files.stem == board.files.stem, std::string(name) + " states its file stem");
        std::size_t connectors = 0;
        for (const BoardSheet& sheet : board.sheets) connectors += sheet.from_module() ? 1 : 0;
        require(connectors > 0, std::string(name) + " has module connector sheets");
        require(board.module.folder == "som" && board.module_definition.pcb == "Zynq_SoM.kicad_pcb" && !board.module_definition.escape_triage.empty(),
                std::string(name) + " reads the shared module folder");
    }
    rejects([&] { load_board(repository / "subsystems"); }, "is missing");
}

}

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: board_definition_contracts REPOSITORY");
        reads_a_board();
        names_board_files();
        refuses_bad_boards();
        reads_a_module();
        refuses_bad_modules();
        loads_a_module_folder();
        reads_the_real_boards(argv[1]);
        std::cout << "board definition contracts: " << checks << " checks passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "board definition contracts FAILED: " << error.what() << "\n";
        return 1;
    }
}
