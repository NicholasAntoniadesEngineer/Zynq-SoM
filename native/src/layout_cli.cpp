#include "schgen/layout_construct.hpp"
#include "schgen/layout_stage.hpp"
#include "schgen/layout_density.hpp"
#include "schgen/layout_squeeze.hpp"
#include "schgen/layout_cli.hpp"
#include "schgen/layout_plan.hpp"

#include "schgen/atomic_file.hpp"
#include "schgen/catalog.hpp"
#include "schgen/geometry_cli.hpp"
#include "schgen/layout_adapter.hpp"
#include "schgen/layout_json.hpp"
#include "schgen/layout_kernel.hpp"
#include "schgen/pcb_emit.hpp"

#include <algorithm>
#include <iostream>
#include <map>

namespace schgen {
namespace {

using layout::LayoutError;

inline constexpr std::size_t report_limit = 20;

const char* const usage =
    "usage: schgen layout-export [--repo DIR] [--project NAME] [--kicad-cli PATH]\n"
    "                            --project-file FILE --plane-net NAME [--overmold-part MPN]... -o FILE\n"
    "       schgen layout-check FILE\n"
    "       schgen layout-construct FILE\n"
    "       schgen layout-arrange FILE\n"
    "       schgen layout-repair FILE\n"
    "       schgen layout-plan FILE\n"
    "  layout-export builds the current placed board and writes it as a layout problem.\n"
    "  layout-check replays a layout problem and reports every hard-rule violation.\n"
    "  layout-construct takes every owned part off the board, seats it again by rule and reports the result.\n"
    "  layout-arrange also takes every free unowned part off the board and places it afresh with its owned parts.\n"
    "  layout-repair runs only the start repair on the placement as handed over and reports what is left.\n"
    "  layout-plan reports how the blocks of a placement sit: wiring between blocks, spread of each block, links that cross.\n";

struct ExportArguments {
    std::filesystem::path repository = std::filesystem::current_path();
    std::optional<std::filesystem::path> project;
    std::string kicad_cli = "kicad-cli", project_file, plane_net, output;
    std::vector<std::string> overmold_parts;
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
              << "layout: " << found.size() << " hard-rule violations, outline "
              << (kernel.outline_holds() ? "holds" : "loses") << " the module and fixed copper\n";
    std::map<std::string, std::pair<std::size_t, double>> tightest;
    for (const auto& margin : kernel.margins()) {
        auto [entry, fresh] = tightest.emplace(margin.kind, std::make_pair(std::size_t{1}, margin.value));
        if (fresh) continue;
        ++entry->second.first;
        entry->second.second = std::min(entry->second.second, margin.value);
    }
    for (const auto& [kind, summary] : tightest)
        std::cout << "layout: " << summary.first << " " << kind << " rules, tightest margin "
                  << summary.second / layout::constants::nano_scale.value << " mm\n";
    for (std::size_t index = 0; index < found.size() && index < report_limit; ++index)
        std::cout << "  " << layout::breach_name(found[index].kind) << " "
                  << problem.parts[found[index].part].reference << " / "
                  << problem.parts[found[index].other].reference << "\n";
    return found.empty() && kernel.outline_holds() ? 0 : 1;
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
        else if (name == "--overmold-part") arguments.overmold_parts.push_back(value);
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
    const auto input = load_geometry_board_inputs(paths, extraction);
    const auto placed = build_pcb_model(input);
    const auto policy = pcb_emit_policy(input.floorplan.project);
    const auto gates = pcb_placement_gate_policy(input);
    const auto binding = layout::bind_model(placed.model, policy, &gates,
        {arguments.plane_net, layout::project_edge_clearance(parse_json_file(arguments.project_file)),
         arguments.overmold_parts, input.floorplan.place_clear, layout::authored_intent(input),
         {input.floorplan.project.density, sheet_densities(load_board(paths.project_root, paths.module))}});
    const std::string text = layout::document_json(binding.problem, binding.placement);
    write_atomic_file(arguments.output, std::vector<uint8_t>(text.begin(), text.end()));
    std::cout << "layout: problem written to " << arguments.output << "\n";
    return report(binding.problem, binding.placement);
}

}

std::optional<int> run_layout_command(int argc, char** argv) {
    if (argc < 2) return std::nullopt;
    const std::string command = argv[1];
    if (command != "layout-export" && command != "layout-check" && command != "layout-construct" && command != "layout-arrange" && command != "layout-repair" && command != "layout-plan" && command != "layout-draw" && command != "layout-lay") return std::nullopt;
    if (std::any_of(argv + 2, argv + argc, [](const char* value) {
            return std::string(value) == "--help" || std::string(value) == "-h";
        })) {
        std::cout << usage;
        return 0;
    }
    if (command == "layout-export") return export_problem(argc, argv);
    if (argc != 3) throw LayoutError(command + ": exactly one problem file is required");
    const auto document = layout::read_document(parse_json_file(argv[2]));
    if (command == "layout-plan") {
        std::cout << layout::plan_figures(document.problem, document.placement).summary();
        return 0;
    }
    if (command == "layout-lay") {
        const layout::Problem dense = layout::without_density(document.problem);
        layout::Kernel kernel(dense, document.placement);
        layout::StageResult repaired;
        layout::repair_start(kernel, layout::default_squeeze(), repaired, [](bool) {});
        const std::size_t before = kernel.violations().size();
        std::cout << "before\n" << layout::plan_figures(dense, kernel.placement()).summary().substr(0, 330) << "\n";
        const layout::LayReport laid = layout::lay_out(kernel);
        std::cout << "laid: " << laid.seated << " of " << laid.clusters << " clusters seated by plan, " << laid.returned << " put back, " << laid.unseated.size()
                  << " without a seat; " << (laid.taken ? "taken" : "not taken") << "; airwire " << layout::to_mm(laid.routed_before) << " to "
                  << layout::to_mm(laid.routed_after) << " mm; weighted " << layout::to_mm(laid.pulled_before) << " to " << layout::to_mm(laid.pulled_after)
                  << "; violations " << before << " before, " << kernel.violations().size() << " after\n";
        std::cout << "  test points left for their own seater: " << laid.deferred << "\n";
        for (const auto& name : laid.unseated) std::cout << "  no seat: " << name << "\n";
        const layout::DrawReport drawn = layout::draw_in(kernel);
        std::cout << "drawn: " << drawn.moved << " moves; weighted " << layout::to_mm(drawn.pulled_before) << " to " << layout::to_mm(drawn.pulled_after)
                  << "; violations " << kernel.violations().size() << "\n";
        std::cout << "after\n" << layout::plan_figures(dense, kernel.placement()).summary() << "\n";
        return 0;
    }
    if (command == "layout-draw") {
        const layout::Problem dense = layout::without_density(document.problem);
        layout::Kernel kernel(dense, document.placement);
        const std::size_t before = kernel.violations().size();
        std::cout << "before\n" << layout::plan_figures(dense, kernel.placement()).summary().substr(0, 400) << "\n";
        const layout::DrawReport drawn = layout::draw_in(kernel);
        std::cout << "drawn: " << drawn.moved << " moves of " << drawn.clusters << " clusters in " << drawn.rounds << " passes; airwire "
                  << layout::to_mm(drawn.routed_before) << " to " << layout::to_mm(drawn.routed_after) << " mm; weighted "
                  << layout::to_mm(drawn.pulled_before) << " to " << layout::to_mm(drawn.pulled_after) << "; violations " << before << " before, "
                  << kernel.violations().size() << " after\n";
        std::cout << "after\n" << layout::plan_figures(dense, kernel.placement()).summary().substr(0, 400) << "\n";
        return 0;
    }
    if (command == "layout-construct" || command == "layout-arrange" || command == "layout-repair") {
        const layout::Problem dense = layout::without_density(document.problem);
        layout::Kernel kernel(dense, document.placement);
        const auto off_face = [&] {
            std::size_t count = 0;
            for (const auto& rule : document.problem.constraints.soft_gaps)
                if (rule.same_face && !layout::pair_faced(document.problem, kernel.board(), rule.anchor, kernel.placement()[rule.anchor],
                                                          rule.member, kernel.placement()[rule.member], rule.or_under))
                    ++count;
            return count;
        };
        const std::size_t faced_before = off_face();
        const std::size_t before = kernel.violations().size();
        if (command != "layout-repair") {
            const auto built = layout::construct_owned(kernel, static_cast<layout::Nm>(layout::constants::search_pitch.value),
                                                       static_cast<layout::Nm>(layout::constants::construct_reach.value), command == "layout-arrange");
            std::cout << layout::construct_summary(built) << "  violations " << before << " before, " << kernel.violations().size() << " after\n"
                      << "  owned parts off their owner's face " << faced_before << " before, " << off_face() << " after\n";
            if (!built.unseated.empty()) return 1;
        }
        layout::StageResult repaired;
        try {
            layout::repair_start(kernel, layout::default_squeeze(), repaired, [](bool) {});
        } catch (const LayoutError& error) {
            std::cout << "  repair: " << error.what() << "\n";
            return 1;
        }
        std::cout << "  after repair: violations " << kernel.violations().size() << ", staged rules left " << layout::start_debt(kernel) << "\n";
        for (const auto& row : repaired.repairs)
            if (!row.kept) std::cout << "    not kept: " << row.rule << " | " << row.subject << " | " << row.action << "\n";
        for (const auto& rule : dense.constraints.soft_gaps)
            if (rule.same_face && !layout::pair_faced(dense, kernel.board(), rule.anchor, kernel.placement()[rule.anchor], rule.member,
                                                       kernel.placement()[rule.member], rule.or_under))
                std::cout << "    left: " << dense.parts[rule.member].reference << " is not on the face of " << dense.parts[rule.anchor].reference << " (" << rule.source << ")\n";
        for (const auto& rule : layout::net_orders_of(dense))
            if (!layout::net_order_met(dense, rule, kernel.placement(), rule.lead, nullptr))
                std::cout << "    left: " << dense.parts[rule.lead].reference << " is not the first part after " << dense.parts[rule.anchor].reference << " (" << rule.source << ")\n";
        for (const auto& violation : kernel.violations())
            std::cout << "    left: " << layout::breach_name(violation.kind) << " " << document.problem.parts[violation.part].reference << "\n";
        return kernel.violations().empty() && layout::start_debt(kernel) == 0 ? 0 : 1;
    }
    return report(document.problem, document.placement);
}

}
