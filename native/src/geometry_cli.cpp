#include "schgen/geometry_cli.hpp"
#include "schgen/board_pipeline.hpp"
#include "schgen/catalog.hpp"

#include <algorithm>
#include <charconv>
#include <iostream>
#include <set>
#include <unistd.h>

namespace schgen {
namespace {
namespace fs = std::filesystem;
bool command(const std::string& value) { return value == "floorplan" || value == "compose"; }
bool prefix(const fs::path& parent, const fs::path& child) {
    auto a = parent.begin(), b = child.begin();
    for (; a != parent.end(); ++a, ++b) if (b == child.end() || *a != *b) return false;
    return true;
}
void safe_file(const fs::path& path) {
    const auto status = fs::symlink_status(path);
    if (fs::is_symlink(status)) throw ProjectError("geometry: symlink output refused: " + path.string());
    if (fs::exists(status) && (!fs::is_regular_file(status) || fs::hard_link_count(path) != 1))
        throw ProjectError("geometry: output must be an unshared regular file: " + path.string());
}
void safe_directory(const fs::path& path) {
    // Inspect the lexical path before canonicalizing: resolving a symlink first
    // would erase precisely the unsafe destination we need to reject.
    auto here = fs::absolute(path).lexically_normal();
    while (!here.empty()) {
        const auto status = fs::symlink_status(here);
        if (fs::is_symlink(status) || (fs::exists(status) && !fs::is_directory(status)))
            throw ProjectError("geometry: unsafe output directory: " + here.string());
        const auto parent = here.parent_path();
        if (parent == here) break;
        here = parent;
    }
}
fs::path output_root(const GeometryCommandOptions& options, const ProjectPaths& paths) {
    const auto result = options.output.empty() ? paths.project_root : fs::absolute(options.output).lexically_normal();
    safe_directory(result);
    if (result == paths.project_root) return result;
    if (prefix(result, paths.repository_root) || prefix(result, paths.project_root))
        throw ProjectError("geometry: output cannot be an ancestor of repository/project inputs");
    for (const auto* name : {"native", "parts", "som", "subsystems", "schgen", "scripts", ".git", ".github"})
        if (prefix(paths.repository_root / name, result)) throw ProjectError("geometry: output overlaps repository sources");
    for (const auto* name : {"subsystems", "research", "firmware"})
        if (prefix(paths.project_root / name, result)) throw ProjectError("geometry: output overlaps project inputs");
    // An isolated output may be reused, but must not be another source project.
    auto here = result;
    while (here != paths.project_root && here != here.parent_path()) {
        if (fs::exists(here / "project.json")) throw ProjectError("geometry: output overlaps another project");
        here = here.parent_path();
    }
    return result;
}
void preflight(const GeometryCommandOptions& options, const ProjectPaths& paths, const fs::path& output) {
    if (options.command == "floorplan") {
        if (options.export_spec) safe_file(output / "floorplan.json");
        else {
            safe_directory(output / "docs");
            safe_file(output / "docs/FLOORPLAN.svg"); safe_file(output / "docs/FLOORPLAN.md");
        }
        return;
    }
    safe_directory(output / "reports");
    safe_file(output / "reports/compose_ledger.json"); safe_file(output / "reports/compose_ledger.md");
    if (!options.compose.repair) return;
    const auto spec = paths.project_root / "floorplan.json";
    safe_directory(spec.parent_path()); safe_file(spec);
    if (!fs::is_regular_file(spec)) throw ProjectError("compose repair requires the selected project's floorplan.json");
    if (options.compose.dry_run) return;
    // The full board pipeline publishes more than the geometry documents.
    // Refuse redirection anywhere in its existing output tree, not just .pcb.
    if (fs::exists(output)) for (const auto& entry : fs::recursive_directory_iterator(output)) {
        if (entry.is_symlink()) throw ProjectError("geometry: symlink in board output tree: " + entry.path().string());
        if (!entry.is_directory()) safe_file(entry.path());
    }
    // The historical in-place board pipeline also ratchets the common carrier
    // fanout ceiling. Its target must pass the same output safety checks.
    if (output == paths.project_root) {
        const auto baseline = paths.repository_root / "carrier/reports/fanout_baseline.json";
        safe_directory(baseline.parent_path()); safe_file(baseline);
    }
}
class Scratch {
public:
    fs::path path;
    Scratch() {
        auto pattern = (fs::temp_directory_path() / "schgen-geometry-XXXXXX").string();
        const auto created = ::mkdtemp(pattern.data());
        if (!created) throw ProjectError("geometry: cannot create private extraction directory");
        path = created;
    }
    Scratch(const Scratch&) = delete;
    Scratch& operator=(const Scratch&) = delete;
    ~Scratch() { std::error_code ignored; fs::remove_all(path, ignored); }
};
}

std::optional<GeometryCommandOptions> parse_geometry_command(int argc, char** argv) {
    int selected = 1;
    while (selected < argc && (std::string(argv[selected]) == "--repo" || std::string(argv[selected]) == "--project")) selected += 2;
    if (selected >= argc || !command(argv[selected])) return std::nullopt;
    GeometryCommandOptions result;
    result.command = argv[selected]; result.repository = fs::current_path();
    std::set<std::string> seen;
    for (int i = 1; i < argc; ++i) {
        if (i == selected) continue;
        const std::string arg = argv[i];
        if (arg == "--help" || arg == "-h") { result.help = true; continue; }
        const auto key = arg == "-o" ? std::string("--output") : arg;
        if (!seen.insert(key).second && key != "--allow-intent") throw ProjectError("duplicate option " + arg);
        if (key == "--export") result.export_spec = true;
        else if (key == "--measure") { /* Legacy default measurement; --repair wins. */ }
        else if (key == "--repair") result.compose.repair = true;
        else if (key == "--dry-run") result.compose.dry_run = true;
        else if (key == "--no-render") result.no_render = true;
        else if (key == "--repo" || key == "--project" || key == "--output" || key == "--kicad-cli" || key == "--allow-intent" || key == "--max-steps") {
            if (++i >= argc || i == selected || !argv[i][0]) throw ProjectError("missing value for " + arg);
            const std::string value = argv[i];
            if (key == "--repo") result.repository = value;
            else if (key == "--project") result.project = value;
            else if (key == "--output") result.output = value;
            else if (key == "--kicad-cli") result.kicad_cli = value;
            else if (key == "--allow-intent") result.compose.allow_intent.push_back(value);
            else {
                // argparse accepts a leading '+', whitespace and negative ints.
                const auto first = value.find_first_not_of(" \t\r\n\v\f"), last = value.find_last_not_of(" \t\r\n\v\f");
                auto number = first == value.npos ? std::string{} : value.substr(first, last - first + 1);
                if (!number.empty() && number.front() == '+') number.erase(0, 1);
                const auto parsed = std::from_chars(number.data(), number.data() + number.size(), result.compose.max_steps);
                if (parsed.ec != std::errc{} || parsed.ptr != number.data() + number.size()) throw ProjectError("expected integer for --max-steps");
            }
        } else throw ProjectError("unknown geometry option: " + arg);
    }
    for (const auto& key : seen) {
        const bool common = key == "--repo" || key == "--project" || key == "--output" || key == "--kicad-cli";
        const bool allowed = result.command == "floorplan" ? key == "--export" : key != "--export";
        if (!common && !allowed) throw ProjectError(key + " is not valid for " + result.command);
    }
    if (!result.help && result.no_render && (!result.compose.repair || result.compose.dry_run))
        throw ProjectError("--no-render is only valid for compose repair apply");
    if (!result.help && result.compose.repair) (void)parse_compose_allow_intent(result.compose.allow_intent);
    return result;
}

std::string geometry_command_help(const std::string& name) {
    if (!command(name)) throw ProjectError("unknown geometry command " + name);
    std::string out = "usage: schgen " + name + " [--repo ROOT] [--project NAME] [--output DIRECTORY] [--kicad-cli PATH]\n"
        "  --help, -h\n  --output, -o DIRECTORY  Artifact root (default: selected project).\n"
        "Fresh native authoring/linking and private KiCad extraction; no cached placed board.\n";
    if (name == "floorplan") return out +
        "  --export  Write CURRENT derived plan to OUTPUT/floorplan.json instead of docs/FLOORPLAN.svg and .md.\n"
        "Existing named outputs are replaced; --export may replace the selected project's editable spec.\n";
    return out +
        "  --measure  Default: measure and append reports/compose_ledger.json and .md.\n"
        "  --repair   Rank edits and apply the best ONE, with full native-policy board gates.\n"
        "  --dry-run  With --repair, rank only; writes ledgers but never edits the spec or runs board.\n"
        "  --allow-intent NAME:FROM->TO  Repeatable, explicit edge-move authorization.\n"
        "  --max-steps INTEGER  Reserved; one edit per invocation (default 4).\n"
        "  --no-render  Apply only: skip optional board rendering, never mandatory gates.\n"
        "--repair overrides --measure. Without --repair, --dry-run/--allow-intent are inert (legacy).\n"
        "Apply edits PROJECT/floorplan.json even with --output; full board artifacts go to OUTPUT.\n"
        "Rejection restores spec bytes, NOT board artifacts. No commit or baseline blessing.\n"
        "In-place apply also uses the board command's common carrier fanout ratchet.\n";
}

PcbPlacementInput load_geometry_board_inputs(const ProjectPaths& paths, const NetlistExtractOptions& extraction) {
    const auto authored = author_board_pipeline_inputs(paths);
    std::vector<CircuitSheetIr> sheets; std::vector<std::string> names;
    for (const auto& circuit : authored.circuits) { sheets.push_back(circuit.circuit); names.push_back(circuit.name); }
    const auto index = extend_sheet_index(load_sheet_index(paths), names).index;
    const auto link = link_sheets(sheets, parse_json_file(paths.som_interface_file.string()),
        parse_json_file((paths.project_root / "som_mapping.json").string()));
    if (!link.ok()) throw ProjectError("geometry link failed: " + link.report());
    std::vector<BoardSheetInput> inputs;
    for (const auto& sheet : sheets) {
        const auto band = std::find_if(index.begin(), index.end(), [&](const auto& entry) { return entry.first == sheet.name; });
        if (band == index.end()) throw ProjectError("geometry sheet index missing " + sheet.name);
        inputs.push_back({sheet, band->second, std::nullopt});
    }
    Scratch scratch;
    SymbolLibrary library(paths.repository_root); BoardSchematicOptions options;
    options.root_name = "Zynq_Carrier"; options.extraction = extraction; options.reports_dir = scratch.path / "reports";
    const auto board = build_board_schematic(inputs, library, scratch.path, options);
    if (!board.ok()) throw ProjectError("geometry schematic gate failed: " + board.report);
    auto input = load_board_inputs(paths, authored.circuits, link, extract_netlist(board.root_path, extraction));
    input.floorplan.sheet_index = index;
    return input;
}

int execute_geometry_command(const GeometryCommandOptions& options) {
    if (!command(options.command)) throw ProjectError("unknown geometry command " + options.command);
    if (options.help) { std::cout << geometry_command_help(options.command); return 0; }
    if (options.compose.repair) (void)parse_compose_allow_intent(options.compose.allow_intent);
    const auto paths = resolve_project_paths(options.repository, options.project);
    const auto output = output_root(options, paths);
    preflight(options, paths, output);
    if (!open_part_catalog(paths.part_catalog_file.string())) throw ProjectError("geometry: cannot open native part catalog");
    NetlistExtractOptions extraction; extraction.kicad_cli = options.kicad_cli;
    if (options.command == "floorplan") {
        const auto input = load_geometry_board_inputs(paths, extraction);
        const auto zones = build_pcb_zone_geometry(input);
        const auto floor = prepare_pcb_floorplan(input, zones);
        const auto plan = build_floorplan(floor);
        // Recheck destinations immediately before publication, after a lengthy solve.
        preflight(options, paths, output);
        if (options.export_spec) {
            const auto path = write_floorplan_spec(plan, output / "floorplan.json");
            std::cout << "floorplan spec: " << path.string() << " (" << plan.edge_blocks.size() << " edge + "
                << plan.interior_blocks.size() << " interior subsystems)\n"
                "FLOORPLAN: declarative spec exported — edit it then re-run `schgen board` to drive the placement\n";
        } else {
            const auto documents = render_floorplan_documents(plan, floor);
            for (const auto& path : write_floorplan_documents(documents, output / "docs")) std::cout << "floorplan: " << path.string() << '\n';
            std::cout << "FLOORPLAN: suggestion written (derived from netlists — see the honest-limits section)\n";
        }
        return 0;
    }
    ComposeCommandHost host;
    host.build_model = [&] {
        auto input = load_geometry_board_inputs(paths, extraction);
        auto placement = build_pcb_model(input);
        preflight(options, paths, output);
        return ComposeBoardSnapshot{std::move(input), std::move(placement.model)};
    };
    host.run_board = [&] {
        preflight(options, paths, output);
        BoardPipelineOptions board; board.output_root = output; board.extraction = extraction;
        board.native_policy = true; board.no_render = options.no_render;
        const auto result = run_board_pipeline(paths, board);
        return ComposeBoardRun{result.exit_code(), result.report()};
    };
    host.output = [](const auto& text) { std::cout << text; };
    return run_compose_command(options.compose,
        {paths.project_root / "floorplan.json", output / "reports/compose_ledger.json", output / "reports/compose_ledger.md"}, host).exit_code;
}

std::optional<int> run_geometry_command(int argc, char** argv) {
    const auto options = parse_geometry_command(argc, argv);
    if (!options) return std::nullopt;
    return execute_geometry_command(*options);
}
} // namespace schgen
