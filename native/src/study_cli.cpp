#include "schgen/study.hpp"

#include "schgen/project_outputs.hpp"

#include <cerrno>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <sys/wait.h>
#include <unistd.h>

namespace schgen {
namespace {

int isolated_board(const RunConfig& config, const std::string& board, const std::filesystem::path& file) {
    std::cout.flush();
    std::cerr.flush();
    const pid_t child = fork();
    if (child < 0) throw std::runtime_error("study layers: cannot start a build process");
    if (child == 0) {
        int status = EXIT_FAILURE;
        try {
            study_stackup(config.stackup_of(board));
            status = run_board(config, board, file);
        } catch (const std::exception& error) {
            std::cerr << "schgen: " << error.what() << "\n";
        }
        std::cout.flush();
        std::cerr.flush();
        std::exit(status);
    }
    int status = 0;
    while (waitpid(child, &status, 0) < 0)
        if (errno != EINTR) throw std::runtime_error("study layers: lost a build process");
    return WIFEXITED(status) ? WEXITSTATUS(status) : -WTERMSIG(status);
}

}

std::optional<int> study_command(int argc, char** argv) {
    if (argc < 2 || std::string(argv[1]) != "study") return std::nullopt;
    std::vector<std::string> arguments(argv + 2, argv + argc);
    if (arguments.empty() || arguments.front() != study::layers_subject)
        throw std::runtime_error(std::string("study needs a subject; known: ") + study::layers_subject + "\n" + run_usage());
    arguments.erase(arguments.begin());
    const RunArguments request = parse_run_arguments(arguments, {study::stackups_option});
    const RunConfig config = load_run_config(request.file);
    const std::vector<std::string> boards = chosen_boards(config, request.boards);
    const std::vector<std::string> names = study::stackups_of(config, request);
    const StackupCatalogue catalogue = load_stackups(stackup_catalogue_file());
    for (const std::string& name : names) catalogue.named(name);
    for (const std::string& board : boards) {
        std::vector<study::Row> rows;
        for (const std::string& name : names) {
            const RunConfig row = study::row_config(config, board, name);
            const std::filesystem::path output = row.output / board, reports = output / study::reports_folder;
            for (const char* report : {study::verdict_report, study::squeeze_report}) std::filesystem::remove(reports / report);
            rows.push_back(study::measured_row(catalogue.named(name), output, isolated_board(row, board, request.file)));
        }
        const std::string table = study::table(board, rows);
        publish_text(study::table_file(config, board, ".txt"), table);
        publish_text(study::table_file(config, board, ".json"), study::document(board, rows));
        std::cout << table;
    }
    return 0;
}

}
