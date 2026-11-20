#include "schgen/project_authoring.hpp"
#include "schgen/sheet_roles.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <set>
#include <stdexcept>
#include <unistd.h>

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

const char* const connector_symbol = "Bench:Connector";
const char* const other_symbol = "Device:R";

const char* const bench_board = R"json({
  "schema": "schgen.board/1",
  "name": "bench",
  "files": {"stem": "Bench_Board"},
  "root_readme": false,
  "owned_groups": false,
  "module": {"folder": "bench_module", "pairs": [], "loads": []},
  "sheets": [
    {"name": "mod_a", "module_connector": "J1", "title": "Module connector one"},
    {"name": "power"},
    {"name": "decoupling"}
  ]
})json";

const char* const bench_module = R"json({
  "schema": "schgen.module/1",
  "schematic": "Bench_Module.kicad_sch",
  "pcb": "Bench_Module.kicad_pcb",
  "connector_part": "Bench",
  "draw": {"connector": "J1", "rail": "VIN", "amps": 2.0, "note": "module supply"},
  "sdio_level_v": 1.8,
  "sd_bus": ["SDIO_CLK"],
  "pairs": [],
  "escape_population": {
    "netted_contacts": {"J1": 1},
    "return_path": {"n_pairs": 1, "n_pair_contacts": 1, "n_fail": 0, "worst_distance": 1}
  },
  "escape_triage": [{"pattern": "X", "class": "GENUINE", "note": "x"}],
  "do_not_load_straps": []
})json";

const char* const quiet_placement =
    R"("placement": {"region": "board", "silk_label": null, "far_guard_mm": null, "escape_basis": null, "escape_escalates": false, "reserves_edge": false})";
const char* const under_placement =
    R"("placement": {"region": "under_module", "silk_label": null, "far_guard_mm": null, "escape_basis": null, "escape_escalates": false, "reserves_edge": false})";
const char* const quiet_checks = R"("checks": {"dividers": [], "divider_sources": [], "iset_window_ma": null})";

struct Bench {
    std::filesystem::path root;
    BoardDefinition board;
    SomInterface module;
    std::vector<CircuitSheetIr> circuits;
    PartFacts facts;
    AuthoringContext context;

    Bench() : root(std::filesystem::temp_directory_path() / ("schgen_sheet_roles_" + std::to_string(getpid()))) {
        std::filesystem::remove_all(root);
        std::filesystem::create_directories(root);
        context.library = root;
        subsystem("power", quiet_placement);
        subsystem("decoupling", under_placement);
        set_board(bench_board);
        module.source = "bench module";
        module.connectors.push_back({"J1", SomConnector{}});
        circuits.push_back(connector_circuit("mod_a", "J1", connector_symbol));
        facts.file = root / "part_facts.json";
        facts.classes.emplace(connector_symbol, PartClass::module_connector);
        facts.classes.emplace(other_symbol, PartClass::resistor);
    }
    ~Bench() { std::filesystem::remove_all(root); }

    void set_board(const std::string& text) {
        board = parse_board(parse_json_text(text), "fixture", parse_module(parse_json_text(bench_module), "fixture module"));
    }
    void subsystem(const std::string& name, const std::string& placement) const {
        std::filesystem::create_directories(root / name);
        std::ofstream(root / name / subsystem_data_file) << "{\"schema\": \"schgen.subsystem/1\", \"name\": \"" << name << "\", " << placement
                                                           << ", " << quiet_checks << "}";
    }
    static CircuitSheetIr connector_circuit(const std::string& sheet, const std::string& reference, const std::string& symbol) {
        CircuitSheetIr circuit;
        circuit.name = sheet;
        CircuitPartIr part;
        part.ref = reference;
        part.lib_id = symbol;
        circuit.parts.push_back(part);
        return circuit;
    }
    SheetRoles roles() const { return sheet_roles(board, context, module, circuits, facts); }
};

void builds_roles() {
    Bench bench;
    const SheetRoles roles = bench.roles();
    require(roles.size() == bench.board.sheets.size(),"every board sheet has a role");
    require(sheet_role(roles, "mod_a").module_connector == "J1" && sheet_role(roles, "mod_a").region == SheetRegion::board,
            "a module connector sheet carries its connector and is board region");
    require(sheet_role(roles, "power").module_connector.empty() && sheet_role(roles, "power").region == SheetRegion::board,
            "an ordinary sheet carries no connector and takes its region from its subsystem file");
    require(sheet_role(roles, "decoupling").region == SheetRegion::under_module, "a subsystem file can place its sheet under the module");
    rejects([&] { sheet_role(roles, "absent"); }, "no role for sheet absent");
}

void refuses_inconsistent_sheets() {
    {
        Bench bench;
        bench.circuits.front().parts.push_back(bench.circuits.front().parts.front());
        rejects([&] { bench.roles(); }, "board bench sheet mod_a: a module connector sheet holds exactly one part, this one holds 2");
    }
    {
        Bench bench;
        bench.circuits.front().parts.clear();
        rejects([&] { bench.roles(); }, "board bench sheet mod_a: a module connector sheet holds exactly one part, this one holds 0");
    }
    {
        Bench bench;
        bench.circuits.front().parts.front().ref = "J9";
        rejects([&] { bench.roles(); }, "board bench sheet mod_a: its part is J9 but board.json states module_connector J1");
    }
    {
        Bench bench;
        bench.circuits.front().parts.front().lib_id = other_symbol;
        rejects([&] { bench.roles(); }, "board bench sheet mod_a: its part J1 has class resistor, not module_connector");
    }
    {
        Bench bench;
        bench.circuits.front().parts.front().lib_id = "Unlisted:Symbol";
        rejects([&] { bench.roles(); }, "Unlisted:Symbol has no class");
    }
    {
        Bench bench;
        bench.circuits.clear();
        rejects([&] { bench.roles(); }, "board bench sheet mod_a: the module connector sheet has no circuit");
    }
}

void refuses_inconsistent_connector_sets() {
    {
        Bench bench;
        bench.module.connectors.push_back({"J2", SomConnector{}});
        rejects([&] { bench.roles(); }, "board bench: no sheet carries module connector J2 of the module interface bench module");
    }
    {
        Bench bench;
        bench.module.connectors.front().first = "J7";
        rejects([&] { bench.roles(); }, "board bench sheet mod_a: module connector J1 is not a connector of the module interface bench module");
    }
    {
        Bench bench;
        bench.set_board(replaced(bench_board, "{\"name\": \"power\"},", "{\"name\": \"mod_b\", \"module_connector\": \"J1\", \"title\": \"Again\"}, {\"name\": \"power\"},"));
        bench.circuits.push_back(Bench::connector_circuit("mod_b", "J1", connector_symbol));
        rejects([&] { bench.roles(); }, "board bench sheet mod_b: module connector J1 is also carried by sheet mod_a");
    }
}

void refuses_missing_regions() {
    {
        Bench bench;
        std::filesystem::remove(bench.root / "power" / subsystem_data_file);
        rejects([&] { bench.roles(); }, "unknown subsystem power");
    }
    {
        Bench bench;
        std::ofstream(bench.root / "power" / subsystem_data_file) << "{\"schema\": \"schgen.subsystem/1\", \"name\": \"power\", " << quiet_checks << "}";
        rejects([&] { bench.roles(); }, "field 'placement' is missing");
    }
}

void reads_the_real_boards(const std::filesystem::path& repository) {
    const PartFacts facts = load_part_facts(repository / "parts" / "part_facts.json");
    const std::set<std::string> under_module{"som_decoupling"};
    for (const char* name : {"carrier", "devkit_mini"}) {
        const std::filesystem::path root = repository / name;
        const BoardDefinition board = load_board(root);
        const SomInterface module = load_som_interface(module_root_of(root) / module_interface_file);
        ProjectAuthoringInput input;
        input.project_root = root;
        input.board = board;
        input.context = make_authoring_context(repository);
        std::vector<CircuitSheetIr> circuits;
        for (const BoardSheet& sheet : board.sheets)
            if (sheet.from_module()) circuits.push_back(author_project_subsystem(name, sheet.name, input));
        const SheetRoles roles = sheet_roles(board, input.context, module, circuits, facts);
        require(roles.size() == board.sheets.size(), std::string(name) + ": every sheet has a role");
        for (const BoardSheet& sheet : board.sheets) {
            const SheetRole& role = sheet_role(roles, sheet.name);
            require(role.module_connector == sheet.module_connector, std::string(name) + ": " + sheet.name + " connector");
            require((role.region == SheetRegion::under_module) == (under_module.count(sheet.name) == 1),
                    std::string(name) + ": " + sheet.name + " region");
        }
        require(sheet_role(roles, "som_j1").module_connector == "J1" && sheet_role(roles, "som_j2").module_connector == "J2" &&
                    sheet_role(roles, "som_j3").module_connector == "J3",
                std::string(name) + ": the three module connector sheets");
        require(sheet_role(roles, "som_decoupling").region == SheetRegion::under_module, std::string(name) + ": decoupling is under the module");
    }
}

}

int main(int argc, char** argv) {
    try {
        if (argc != 3) throw std::runtime_error("usage: sheet_roles_contracts <repository> <catalog>");
        if (!open_part_catalog(argv[2])) throw std::runtime_error("the part catalog " + std::string(argv[2]) + " does not open");
        builds_roles();
        refuses_inconsistent_sheets();
        refuses_inconsistent_connector_sets();
        refuses_missing_regions();
        reads_the_real_boards(argv[1]);
        std::cout << "sheet roles contracts: " << checks << " checks passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "sheet roles contracts FAILED: " << error.what() << "\n";
        return 1;
    }
}
