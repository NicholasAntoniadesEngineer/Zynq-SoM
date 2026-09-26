#include "schgen/board_pcb.hpp"
#include "schgen/pcb_verification.hpp"
#include <fstream>
#include <iostream>
#include <iterator>

namespace {
std::string read(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot read " + path.string());
    return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}
void equal(const std::filesystem::path& actual, const std::filesystem::path& expected) {
    if (read(actual) != read(expected)) throw std::runtime_error("publication differs: " + actual.string());
}
}

int main(int argc, char** argv) {
    using namespace schgen;
    try {
        if (argc != 3) throw std::runtime_error("usage: board_live_contracts REPOSITORY SCRATCH");
        const auto root = std::filesystem::absolute(argv[1]);
        if (PcbVerificationResult{}.ok()) throw std::runtime_error("unexecuted aggregate cannot pass");
        for (const auto* project : {"carrier", "devkit_mini"}) {
            const auto paths = resolve_project_paths(root, std::filesystem::path(project));
            const auto stage = prepare_board_pcb(paths);
            std::ifstream expected(paths.project_root / "Zynq_Carrier.kicad_pcb", std::ios::binary);
            if (!expected) throw std::runtime_error("missing committed board reference");
            const std::string bytes((std::istreambuf_iterator<char>(expected)), std::istreambuf_iterator<char>());
            if (bytes != stage.emission.pcb) throw std::runtime_error(std::string(project) + ": live native board differs from reference");
            const auto output = std::filesystem::path(argv[2]) / project;
            std::filesystem::create_directories(output);
            std::filesystem::copy_file(paths.project_root / "Zynq_Carrier.kicad_pro",
                output / "Zynq_Carrier.kicad_pro", std::filesystem::copy_options::overwrite_existing);
            publish_board_pcb(stage, output);
            for (const auto* name : {"Zynq_Carrier.kicad_pcb", "Zynq_Carrier.kicad_pro",
                                      "docs/FLOORPLAN.md", "docs/FLOORPLAN.svg"})
                equal(output / name, paths.project_root / name);
            equal(output / "manufacturing/Zynq_Carrier_pcb.kicad_dru",
                root / "native/tests/data/pcb_emit" / (std::string(project) + ".kicad_dru"));
            PcbEmittedBoard emitted{(output / "Zynq_Carrier.kicad_pcb").string(),
                sexpr_loads(read(output / "Zynq_Carrier.kicad_pcb")), true};
            const auto checks = verify_pcb_geometry(stage, emitted, 0);
            if (!checks.ok()) throw std::runtime_error(std::string(project) + ": independent PCB aggregate failed");
            const auto report = [&](const std::string& text, const std::string& filename) {
                if (text + "\n" != read(paths.reports_dir / filename))
                    throw std::runtime_error("independent native report differs: " + filename);
            };
            report(checks.ratsnest.summary(), "ratsnest.txt");
            report(checks.placement.placement_contract.summary(), "placement_contract.txt");
            report(checks.placement.placement_flow.summary(), "placement_flow.txt");
            report(checks.placement.coverage_report.text, "contract_coverage.txt");
            report(checks.placement.composition.text(), "floorplan_composition.txt");
            report(checks.return_stitch.summary(), "return_stitch.txt");
            report(checks.escape_lanes.summary(), "escape_lanes.txt");
            report(checks.fanout.summary(), "fanout.txt");
            if (checks.return_path.ok || checks.return_path.n_fail() != 29)
                throw std::runtime_error("fixed SoM return-path debt must remain visible");
            emitted.exists = false;
            bool rejected = false;
            try { verify_pcb_geometry(stage, emitted, 0); }
            catch (const ProjectError&) { rejected = true; }
            if (!rejected) throw std::runtime_error("missing emitted board must fail");
            std::cout << project << ": live extraction -> immutable inputs -> native placement -> exact PCB PASS\n";
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
