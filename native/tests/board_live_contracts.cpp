#include "schgen/board_pcb.hpp"
#include <fstream>
#include <iostream>
#include <iterator>

int main(int argc, char** argv) {
    using namespace schgen;
    try {
        if (argc != 2) throw std::runtime_error("usage: board_live_contracts REPOSITORY");
        const auto root = std::filesystem::absolute(argv[1]);
        for (const auto* project : {"carrier", "devkit_mini"}) {
            const auto paths = resolve_project_paths(root, std::filesystem::path(project));
            const auto stage = prepare_board_pcb(paths);
            std::ifstream expected(paths.project_root / "Zynq_Carrier.kicad_pcb", std::ios::binary);
            if (!expected) throw std::runtime_error("missing committed board reference");
            const std::string bytes((std::istreambuf_iterator<char>(expected)), std::istreambuf_iterator<char>());
            if (bytes != stage.emission.pcb) throw std::runtime_error(std::string(project) + ": live native board differs from reference");
            std::cout << project << ": live extraction -> immutable inputs -> native placement -> exact PCB PASS\n";
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
