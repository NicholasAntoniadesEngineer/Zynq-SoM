#include "schgen/layout_cli.hpp"

#include "schgen/atomic_file.hpp"
#include "schgen/catalog.hpp"
#include "schgen/geometry_cli.hpp"
#include "schgen/layout_adapter.hpp"
#include "schgen/layout_json.hpp"
#include "schgen/layout_kernel.hpp"
#include "schgen/pcb_emit.hpp"

#include <algorithm>
#include <iostream>

namespace schgen {
namespace {

using layout::LayoutError;

inline constexpr std::size_t report_limit = 20;

const char* const usage =
    "usage: schgen layout-export [--repo DIR] [--project NAME] [--kicad-cli PATH]\n"
    "                            --project-file FILE --plane-net NAME -o FILE\n"
    "       schgen layout-check FILE\n"
    "  layout-export builds the current placed board and writes it as a layout problem.\n"
    "  layout-check replays a layout problem and reports every hard-rule violation.\n";

struct ExportArguments {
    std::filesystem::path repository = std::filesystem::current_path();
    std::optional<std::filesystem::path> project;
    std::string kicad_cli = "kicad-cli", project_file, plane_net, output;
};

int report(const layout::Problem& problem, const layout::Placement& placement) {
    const layout::Kernel kernel(problem, placement);
    const auto found = kernel.violations();
    const auto length = kernel.measured_wirelength();
    std::cout << "layout: " << layout::to_mm(problem.board.width) << " x " << layout::to_mm(problem.board.height)
              << " mm, " << problem.parts.size() << " parts, " << problem.nets.size() << " nets, "
              << problem.obstacles.size() << " fixed copper items\n"
              << "layout: airwire mm signal " << layout::to_mm(length.signal) << " power "
              << layout::to_mm(length.power) << " plane " << layout::to_mm(length.plane) << "\n"
              << "layout: " << found.size() << " hard-rule violations\n";
    for (std::size_t index = 0; index < found.size() && index < report_limit; ++index)
        std::cout << "  " << layout::breach_name(found[index].kind) << " "
                  << problem.parts[found[index].part].reference << " / "
                  << problem.parts[found[index].other].reference << "\n";
    return found.empty() ? 0 : 1;
}

int export_problem(int argc, char** argv) {
    ExportArguments arguments;
    for (int index = 2; index < argc; ++index) {
        const std::string name = argv[index];
        if (index + 1 == argc) throw LayoutError("layout-export: " + name + " requires a value");
        const std::string value = argv[++index];
        if (name == "--repo") arguments.repository = value;
        else if (name == "--project") arguments.project = value;
        else if (name == "--kicad-cli") arguments.kicad_cli = value;
        else if (name == "--project-file") arguments.project_file = value;
        else if (name == "--plane-net") arguments.plane_net = value;
        else if (name == "-o" || name == "--output") arguments.output = value;
        else throw LayoutError("layout-export: unknown option " + name);
    }
    if (arguments.project_file.empty() || arguments.plane_net.empty() || arguments.output.empty())
        throw LayoutError("layout-export: --project-file, --plane-net and -o are required");
    const auto paths = resolve_project_paths(arguments.repository, arguments.project);
    if (!open_part_catalog(paths.part_catalog_file.string()))
        throw LayoutError("layout-export: cannot open the part catalog");
    NetlistExtractOptions extraction;
    extraction.kicad_cli = arguments.kicad_cli;
    const auto placed = build_pcb_model(load_geometry_board_inputs(paths, extraction));
    const auto policy = pcb_emit_policy(load_project_config(paths));
    const auto binding = layout::bind_model(placed.model, policy,
        {arguments.plane_net, layout::project_edge_clearance(parse_json_file(arguments.project_file))});
    const std::string text = layout::document_json(binding.problem, binding.placement);
    write_atomic_file(arguments.output, std::vector<uint8_t>(text.begin(), text.end()));
    std::cout << "layout: problem written to " << arguments.output << "\n";
    return report(binding.problem, binding.placement);
}

}

std::optional<int> run_layout_command(int argc, char** argv) {
    if (argc < 2) return std::nullopt;
    const std::string command = argv[1];
    if (command != "layout-export" && command != "layout-check") return std::nullopt;
    if (std::any_of(argv + 2, argv + argc, [](const char* value) {
            return std::string(value) == "--help" || std::string(value) == "-h";
        })) {
        std::cout << usage;
        return 0;
    }
    if (command == "layout-export") return export_problem(argc, argv);
    if (argc != 3) throw LayoutError("layout-check: exactly one problem file is required");
    const auto document = layout::read_document(parse_json_file(argv[2]));
    return report(document.problem, document.placement);
}

}
