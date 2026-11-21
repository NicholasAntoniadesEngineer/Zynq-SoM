#include "schgen/assembly_refresh.hpp"

#include "schgen/board_pipeline.hpp"
#include "schgen/bom.hpp"
#include "schgen/catalog.hpp"
#include "schgen/project.hpp"
#include "schgen/project_outputs.hpp"
#include "schgen/run_config.hpp"

#include <iostream>
#include <set>

namespace schgen {
namespace {
const char* const command_name = "assembly-refresh";
const char* const usage_text =
    "usage: schgen assembly-refresh [--config FILE] [--repo DIR] [--code CODE]... [--only] [--dry-run]\n"
    "  Reads every order code on every board's BOM (boards named in the run config) from JLCPCB's\n"
    "  assembly library and LCSC, and rewrites parts/assembly_facts.json. A code that cannot be read keeps\n"
    "  its old row and is reported. --code adds a code that is on no BOM yet. --only reads just the --code list. --dry-run prints the diff only.\n";
}

std::optional<int> run_assembly_refresh_command(int argc, char** argv) {
    if (argc < 2 || std::string(argv[1]) != command_name) return std::nullopt;
    std::filesystem::path config_file = run_config_file, repository = std::filesystem::current_path();
    std::set<std::string> codes;
    bool dry = false, only = false;
    for (int index = 2; index < argc; ++index) {
        const std::string option = argv[index];
        if (option == "--help" || option == "-h") { std::cout << usage_text; return 0; }
        if (option == "--dry-run") { dry = true; continue; }
        if (option == "--only") { only = true; continue; }
        if (option != "--config" && option != "--repo" && option != "--code") throw std::runtime_error("unknown assembly-refresh option " + option);
        if (++index == argc) throw std::runtime_error(option + " needs a value");
        if (option == "--config") config_file = argv[index];
        else if (option == "--repo") repository = argv[index];
        else codes.insert(argv[index]);
    }
    const RunConfig config = load_run_config(config_file);
    if (!open_part_catalog((repository / "native/catalog.bin").string())) throw std::runtime_error("cannot open the part catalog");
    for (const std::string& board : only ? std::vector<std::string>{} : config.boards) {
        ProjectPaths paths = resolve_project_paths(repository, board);
        paths.run_config = std::filesystem::absolute(config_file);
        std::vector<CircuitSheetIr> sheets;
        for (const auto& circuit : author_board_pipeline_inputs(paths).circuits) sheets.push_back(circuit.circuit);
        for (const BomRow& row : generate_bom(sheets).rows)
            if (!row.lcsc.empty()) codes.insert(row.lcsc);
    }
    const std::filesystem::path file = repository / "parts" / assembly_facts_name;
    const AssemblyFacts old = load_assembly_facts(file);
    const AssemblyRefreshResult result = refresh_assembly_facts(old, std::vector<std::string>(codes.begin(), codes.end()), live_assembly_transport(), assembly_utc_now);
    for (const std::string& line : result.changes) std::cout << "changed " << line << '\n';
    for (const std::string& line : result.failures) std::cout << "FAILED " << line << '\n';
    std::cout << codes.size() << " codes read, " << result.changes.size() << " changed, " << result.failures.size() << " failed\n";
    if (!dry) publish_text(file, assembly_facts_text(result.facts));
    return result.failures.empty() ? 0 : 1;
}

}
