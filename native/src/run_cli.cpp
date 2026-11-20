#include "schgen/run_config.hpp"

#include "schgen/project_cli.hpp"

#include <iostream>
#include <set>
#include <stdexcept>

namespace schgen {

std::optional<int> run_config_command(int argc, char** argv) {
    const bool bare = argc == 1;
    if (!bare && std::string(argv[1]) != "run") return std::nullopt;
    std::filesystem::path file = run_config_file;
    std::vector<std::string> chosen;
    for (int index = 2; index < argc; ++index) {
        const std::string argument = argv[index];
        if (argument == "--config") {
            if (++index == argc) run_config_failure("--config needs a file");
            file = argv[index];
        } else if (argument.rfind("--", 0) == 0) {
            run_config_failure("unknown option " + argument + "; settings belong in the file");
        } else {
            chosen.push_back(argument);
        }
    }
    const RunConfig config = load_run_config(file);
    const std::set<std::string> known(config.boards.begin(), config.boards.end());
    for (const std::string& board : chosen)
        if (!known.count(board)) run_config_failure("board '" + board + "' is not listed under 'boards'");
    int status = 0;
    for (const std::string& board : chosen.empty() ? config.boards : chosen) {
        std::vector<std::string> arguments = config.board_arguments(board, file);
        std::vector<char*> raw;
        for (std::string& argument : arguments) raw.push_back(argument.data());
        std::cout << "== " << board << " on " << config.stackup_of(board) << " ==\n";
        const auto result = run_project_command(static_cast<int>(raw.size()), raw.data());
        if (!result) throw std::logic_error("the board command did not run");
        if (*result != 0) status = *result;
    }
    return status;
}

}
