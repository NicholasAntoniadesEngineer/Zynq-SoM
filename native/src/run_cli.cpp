#include "schgen/run_config.hpp"

#include "schgen/catalog.hpp"
#include "schgen/project_catalog.hpp"
#include "schgen/project_cli.hpp"

#include <filesystem>
#include <iostream>
#include <stdexcept>

namespace schgen {

int run_board(const RunConfig& config, const std::string& board) {
    const ProjectCatalogPaths catalogue = project_catalog_paths(std::filesystem::current_path(), board);
    if (!compile_part_catalog(catalogue.parts_dir.string(), catalogue.part_catalog.string()))
        throw std::runtime_error("the part catalogue could not be compiled from " + catalogue.parts_dir.string());
    std::vector<std::string> arguments = config.board_arguments(board);
    std::vector<char*> raw;
    for (std::string& argument : arguments) raw.push_back(argument.data());
    std::cout << "== " << board << " on " << config.stackup_of(board) << " ==\n";
    const auto result = run_project_command(static_cast<int>(raw.size()), raw.data());
    if (!result) throw std::logic_error("the board command did not run");
    return *result;
}

std::optional<int> run_config_command(int argc, char** argv) {
    const bool bare = argc == 1;
    if (!bare && std::string(argv[1]) != "run") return std::nullopt;
    const RunArguments request = parse_run_arguments(bare ? std::vector<std::string>{} : std::vector<std::string>(argv + 2, argv + argc), {});
    const RunConfig config = load_run_config(request.file);
    int status = 0;
    for (const std::string& board : chosen_boards(config, request.boards)) {
        const int result = run_board(config, board);
        if (result != 0) status = result;
    }
    return status;
}

}
