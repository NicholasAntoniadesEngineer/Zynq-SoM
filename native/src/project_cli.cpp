#include "schgen/project_cli.hpp"

#include "schgen/bom.hpp"
#include "schgen/board_schematic.hpp"
#include "schgen/board_pcb.hpp"
#include "schgen/board_pipeline.hpp"
#include "schgen/subsystem_build.hpp"
#include "schgen/example_devkit.hpp"
#include "schgen/experiment_tools.hpp"
#include "schgen/net_contract.hpp"
#include "schgen/pcb_drc.hpp"
#include "schgen/subsystem_scaffold.hpp"
#include "schgen/native_render.hpp"
#include "schgen/model3d.hpp"
#include "schgen/assembly_documents.hpp"
#include "schgen/manufacturing_checks.hpp"
#include "schgen/procurement.hpp"
#include "schgen/ratsnest_documents.hpp"
#include "schgen/gallery.hpp"
#include "schgen/diagram.hpp"
#include "schgen/constraints.hpp"
#include "schgen/part_checks.hpp"
#include "schgen/bom_values.hpp"
#include "schgen/footprint_pads.hpp"
#include "schgen/pin_completeness.hpp"
#include "schgen/symbol_law.hpp"
#include "schgen/spice.hpp"
#include "schgen/firmware_docs.hpp"
#include "schgen/devicetree.hpp"
#include "schgen/design_rules.hpp"
#include "schgen/link.hpp"
#include "schgen/project.hpp"
#include "schgen/project_outputs.hpp"
#include "schgen/som_interface.hpp"
#include "schgen/vivado.hpp"
#include "schgen/validation.hpp"
#include "schgen/selftest_full.hpp"
#include "schgen/process.hpp"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <iostream>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include <unistd.h>

namespace schgen {
namespace {
namespace fs = std::filesystem;
struct Options {
    std::string command, refs = "J1,J2,J3", kicad_cli = "kicad-cli";
    fs::path repository = fs::current_path(), som, contract, output, xdc, pcb;
    std::optional<fs::path> project;
    std::vector<std::string> subsystems;
    bool allow_missing = false, qualified_refs = false, no_ngspice = false, keep = false;
    bool no_render = false, timing = false, conservative_only = false;
    bool help = false;
    std::set<std::string> help_options;
    long long quantity = 1, minimum_stock = 50;
};
const std::set<std::string> commands{"selftest", "project-check", "circuit-check", "som-interface", "xdc", "vivado", "fpga", "bom", "link", "devicetree", "design-rules", "testpoints", "board-schematic", "pcb-stage", "pcb-drc", "subsystem-new", "render3d", "board-step", "model3d-check", "assembly", "ratsnest", "gallery", "diagram", "si-constraints", "fab-profile", "manifest", "preflight", "constraints", "powertree", "thermal", "part-rules", "bom-values", "footprint-pads", "pin-completeness", "symbol-law", "spice", "firmware", "manual", "scfw", "testplan", "power-sequence"};
bool experiment_command(const std::string& name){
    return name=="chir-rung"||name=="w11-sweep"||name=="w12-bound"||name=="w12-stageprobe"||name=="dump-circuits";
}
bool project_command(const std::string& name){
    return commands.count(name)||experiment_command(name)||name=="board"||name=="build"||name=="devkit"||name=="nets"||name=="subsystem-check"||name=="carrier-check";
}
Options parse(int argc, char** argv) {
    Options out;
    std::set<std::string> seen;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (project_command(arg) && out.command.empty()) { out.command = arg; continue; }
        if(arg=="--help"||arg=="-h"){out.help=true;continue;}
        if(arg=="--cons-only"){
            if(!seen.insert(arg).second)throw ProjectError("duplicate option "+arg);
            out.conservative_only=true;continue;
        }
        if (arg == "--no-render" || arg == "--timing") {
            if (!seen.insert(arg).second) throw std::runtime_error("duplicate option " + arg);
            if (arg == "--no-render") out.no_render = true;
            else out.timing = true;
            continue;
        }
        if (arg == "--allow-missing" || arg == "--qualified-refs" || arg == "--no-ngspice" || arg == "--keep") {
            if (!seen.insert(arg).second) throw std::runtime_error("duplicate option " + arg);
            if (arg == "--allow-missing") out.allow_missing = true;
            else if (arg == "--qualified-refs") out.qualified_refs = true;
            else if (arg == "--keep") out.keep = true;
            else out.no_ngspice = true;
            continue;
        }
        if (arg == "--repo" || arg == "--project" || arg == "--som" ||
            arg == "--contract" || arg == "--output" || arg == "-o" ||
            arg == "--xdc" || arg == "--refs" || arg == "--kicad-cli" || arg == "--pcb" ||
            arg == "--subsystem" || arg == "--qty" || arg == "--min-stock") {
            if (++i == argc) throw std::runtime_error("missing value for " + arg);
            const std::string key = arg == "-o" ? "--output" : arg;
            if (arg != "--subsystem" && !seen.insert(key).second)
                throw std::runtime_error("duplicate option " + arg);
            const std::string value = argv[i];
            if (value.empty()) throw std::runtime_error("empty value for " + arg);
            if (arg == "--repo") out.repository = value;
            else if (arg == "--project") out.project = value;
            else if (arg == "--som") out.som = value;
            else if (arg == "--contract") out.contract = value;
            else if (arg == "--output" || arg == "-o") out.output = value;
            else if (arg == "--xdc") out.xdc = value;
            else if (arg == "--pcb") out.pcb = value;
            else if (arg == "--refs") out.refs = value;
            else if (arg == "--kicad-cli") out.kicad_cli = value;
            else if (arg == "--qty" || arg == "--min-stock") {
                std::size_t used = 0;
                const auto number = std::stoll(value, &used);
                if (used != value.size()) throw ProjectError("expected integer for " + arg);
                if (arg == "--qty") out.quantity = number;
                else out.minimum_stock = number;
            }
            else out.subsystems.push_back(value);
        } else if (!arg.empty() && arg[0] != '-' && !out.command.empty()) {
            out.subsystems.push_back(arg);
        } else throw std::runtime_error("unknown project command or option: " + arg);
    }
    if (out.command.empty()) throw std::runtime_error("missing project command; use --help");
    std::set<std::string> allowed{"--repo", "--project"};
    const bool check_only = out.command == "project-check" || out.command == "circuit-check";
    if (!check_only) allowed.insert("--output");
    if(experiment_command(out.command)){
        allowed.erase("--output");allowed.insert("--kicad-cli");
        if(out.command=="w12-stageprobe")allowed.insert("--cons-only");
    } else if (out.command == "board") {
        allowed.insert("--no-render"); allowed.insert("--timing"); allowed.insert("--kicad-cli");
    } else if (out.command == "build" || out.command == "devkit") {
        allowed.insert("--no-render"); allowed.insert("--kicad-cli");
        if(out.command=="devkit")allowed.erase("--project");
    } else if (out.command == "subsystem-check" || out.command == "carrier-check") {
        allowed.erase("--output");
    } else if (out.command == "nets") {
        // Explicit selected-project net header; no SoM extraction overrides.
    } else if (out.command == "preflight") {
        allowed.insert("--qty"); allowed.insert("--min-stock"); allowed.insert("--allow-missing");
    } else if (out.command == "bom") {
        allowed.insert("--allow-missing"); allowed.insert("--qualified-refs");
    } else if (out.command == "link" || out.command == "diagram") {
        allowed.insert("--contract");
    } else if (out.command == "gallery") {
        allowed.erase("--output");
    } else if (out.command == "pcb-drc") {
        allowed.insert("--pcb");
    } else if (out.command == "subsystem-new") {
        allowed.erase("--project"); allowed.erase("--output");
    } else if (out.command == "render3d" || out.command == "board-step") {
        allowed.insert("--pcb"); allowed.insert("--kicad-cli");
    } else if (out.command == "model3d-check") {
        // Checks the selected project's real model inventory.
    } else if (out.command == "board-schematic" || out.command == "selftest" || out.command == "pcb-stage" || out.command == "assembly" || out.command == "ratsnest") {
        allowed.insert("--kicad-cli");
        if (out.command == "selftest") allowed.insert("--keep");
    } else if (out.command == "thermal" || out.command == "powertree" || out.command == "part-rules") {
        if (out.command == "thermal") allowed.insert("--pcb");
    } else if (out.command == "spice") {
        allowed.insert("--no-ngspice");
    } else if (out.command == "firmware" || out.command == "manual" || out.command == "scfw" || out.command == "manifest") {
        allowed.insert("--kicad-cli");
    } else if (out.command == "testplan" || out.command == "power-sequence" || out.command == "si-constraints" || out.command == "fab-profile") {
        // Pure document stages use the selected circuits.
    } else if (out.command == "bom-values" || out.command == "footprint-pads" ||
               out.command == "pin-completeness" || out.command == "symbol-law") {
        // These checks consume the selected circuits, not a live SoM map.
    } else if (!check_only && out.command != "design-rules" && out.command != "testpoints" && out.command != "constraints") {
        allowed.insert("--som"); allowed.insert("--refs"); allowed.insert("--kicad-cli");
        if (out.command != "som-interface") allowed.insert("--contract");
        if (out.command == "vivado" || out.command == "fpga") allowed.insert("--xdc");
    }
    for (const auto& key : seen) {
        if (!allowed.count(key)) throw std::runtime_error(key + " is not valid for " + out.command);
    }
    out.help_options=std::move(allowed);
    return out;
}
std::vector<std::string> refs(const std::string& text) {
    std::vector<std::string> out;
    std::size_t start = 0;
    while (start <= text.size()) {
        const auto end = text.find(',', start);
        auto part = text.substr(start, end == std::string::npos ? end : end - start);
        const auto first = part.find_first_not_of(" \r\n\t");
        if (first != std::string::npos) {
            part = part.substr(first, part.find_last_not_of(" \r\n\t") - first + 1);
            if (std::find(out.begin(), out.end(), part) != out.end())
                throw std::runtime_error("duplicate connector reference " + part);
            out.push_back(std::move(part));
        }
        if (end == std::string::npos) break;
        start = end + 1;
    }
    if (out.empty()) throw std::runtime_error("at least one connector reference is required");
    return out;
}
}

std::optional<int> run_project_command(int argc, char** argv) {
    if (argc < 2) return std::nullopt;
    const std::string first = argv[1];
    if (!project_command(first) && first != "--repo" && first != "--project") return std::nullopt;
    const auto options = parse(argc, argv);
    if(options.help){
        std::cout<<"usage: schgen "<<options.command;
        if(options.command=="build"||options.command=="subsystem-new")std::cout<<" NAME";
        else if(experiment_command(options.command)&&options.command!="dump-circuits")std::cout<<(options.command=="w11-sweep"?" MM":" TAG")<<" [SHEET ...]";
        std::cout<<" [options]\nOptions:\n  --help, -h\n";
        const std::set<std::string> flags={"--no-render","--timing","--cons-only","--allow-missing","--qualified-refs","--no-ngspice","--keep"};
        for(const auto& option:options.help_options)std::cout<<"  "<<option<<(flags.count(option)?"":" VALUE")<<(option=="--output"?" (alias -o)":"")<<'\n';
        if(options.command=="nets"||options.command=="devkit"||options.command=="board-schematic"||options.command=="pcb-stage")std::cout<<"--output is required.\n";
        if(options.command=="devkit")std::cout<<"Builds the four-sheet example, not the twelve-sheet devkit_mini project.\n";
        if(options.command=="chir-rung"||options.command=="w11-sweep")std::cout<<"Publishes board artifacts; restores input spec and fallback baseline. Diagnostic pass=False is not a successful board gate.\n";
        return 0;
    }
    if (options.command == "subsystem-new") {
        if (options.subsystems.size() != 1) throw ProjectError("subsystem-new requires exactly one package name");
        const auto result = scaffold_subsystem(fs::absolute(options.repository) / "subsystems", options.subsystems.front());
        std::cout << subsystem_scaffold_summary(result);
        return 0;
    }
    if(options.command=="devkit"){
        if(!options.subsystems.empty()||options.output.empty())throw ProjectError("devkit requires --output DIRECTORY and no subsystem selection");
        const auto repository=fs::absolute(options.repository);
        if(!open_part_catalog((repository/"native/catalog.bin").string()))throw ProjectError("cannot open native part catalog");
        const auto sheets=author_example_devkit(make_authoring_context(repository));
        SymbolLibrary library(repository);ExampleDevkitOptions build;
        build.no_render=options.no_render;build.extraction.kicad_cli=options.kicad_cli;
        const auto result=build_example_devkit(sheets,library,options.output,build);
        std::cout<<result.report;return result.ok()?0:1;
    }
    const auto paths = resolve_project_paths(options.repository, options.project);
    const auto config = load_project_config(paths);
    if(options.command=="subsystem-check"||options.command=="carrier-check"){
        if(!options.subsystems.empty())throw ProjectError(options.command+" takes no subsystem selection");
        if(!open_part_catalog((paths.repository_root/"native/catalog.bin").string()))throw ProjectError("cannot open native part catalog");
        if(options.command=="subsystem-check"){
            const auto result=check_subsystem_structure(paths.repository_root/"subsystems",
                native_subsystem_factories(make_authoring_context(paths.repository_root)),AuthoringPackageMode::native_assets);
            std::cout<<result.summary()<<'\n';return result.exit_code(true);
        }
        const auto authored=author_board_pipeline_inputs(paths);
        const auto result=check_carrier_structure(paths.subsystems_dir,paths.repository_root/"subsystems",
            authored.factories,AuthoringPackageMode::native_assets);
        std::cout<<result.summary()<<'\n';return result.exit_code();
    }
    if(options.command=="nets"){
        if(options.output.empty()||!options.subsystems.empty())throw ProjectError("nets requires --output HEADER and no subsystem selection");
        const auto result=write_net_contract_header(load_net_contract_input(paths),options.output);
        std::cout<<"NET CONTRACT: "<<result.som.size()<<" SoM nets, "<<result.rails.size()<<" rails -> "<<options.output.string()<<'\n';
        return 0;
    }
    if(experiment_command(options.command)){
        if(!open_part_catalog((paths.repository_root/"native/catalog.bin").string()))throw ProjectError("cannot open native part catalog");
        if(options.command=="dump-circuits"){
            if(!options.subsystems.empty())throw ProjectError("dump-circuits takes no subsystem selection");
            std::cout<<run_dump_circuits(paths,paths.project_root.filename().string());return 0;
        }
        if(options.subsystems.empty())throw ProjectError(options.command+" requires a tag or ordinary-via cost");
        const auto argument=options.subsystems.front();
        const std::vector<std::string> selected(options.subsystems.begin()+1,options.subsystems.end());
        if(options.command=="chir-rung"||options.command=="w11-sweep"){
            ExperimentBoardPaths files{paths.project_root/"floorplan.json",paths.reports_dir/"fallback_baseline.json",
                paths.project_root/"Zynq_Carrier.kicad_pcb",paths.reports_dir/"experiment_verdicts.json"};
            ExperimentBoardHost host;
            host.run_board=[&](const ExperimentBoardRequest& request){
                BoardPipelineOptions build;build.native_policy=true;build.no_render=request.no_render;
                build.extraction.kicad_cli=options.kicad_cli;
                if(request.ordinary_via_mm){auto experiment=std::make_shared<FloorplanExperiment>();
                    experiment->ordinary_via_mm=request.ordinary_via_mm;build.pcb.experiment=std::move(experiment);}
                const auto result=run_board_pipeline(paths,build);
                return ExperimentBoardRun{result.exit_code(),result.report(),{}};
            };
            const auto result=options.command=="chir-rung"?run_chir_rung(files,host,argument,selected):
                run_w11_sweep(files,host,argument,selected);
            std::cout<<result.output;return 0;
        }
        // Probes author and extract fresh connectivity in private scratch; the
        // source project's circuit snapshots, board and baselines stay intact.
        struct ProbeScratch{fs::path path;~ProbeScratch(){std::error_code ignored;fs::remove_all(path,ignored);}};
        auto pattern=(fs::temp_directory_path()/"schgen-probe-XXXXXX").string();
        const auto created=::mkdtemp(pattern.data());if(!created)throw ProjectError("cannot create probe scratch");
        ProbeScratch scratch{created};
        const auto authored=author_board_pipeline_inputs(paths);
        std::vector<CircuitSheetIr> sheets;std::vector<std::string> names;
        for(const auto& circuit:authored.circuits){sheets.push_back(circuit.circuit);names.push_back(circuit.name);}
        const auto index=extend_sheet_index(load_sheet_index(paths),names).index;
        const auto link=link_sheets(sheets,parse_json_file(paths.som_interface_file.string()),
            parse_json_file((paths.project_root/"som_mapping.json").string()));
        if(!link.ok())throw ProjectError("probe link failed: "+link.report());
        std::vector<BoardSheetInput> inputs;
        for(const auto& sheet:sheets){const auto band=std::find_if(index.begin(),index.end(),[&](const auto& entry){return entry.first==sheet.name;});
            if(band==index.end())throw ProjectError("probe sheet index missing "+sheet.name);
            inputs.push_back({sheet,band->second,std::nullopt});}
        SymbolLibrary library(paths.repository_root);BoardSchematicOptions schematic;
        schematic.root_name="Zynq_Carrier";schematic.extraction.kicad_cli=options.kicad_cli;
        schematic.reports_dir=scratch.path/"reports";
        const auto board=build_board_schematic(inputs,library,scratch.path,schematic);
        if(!board.ok())throw ProjectError("probe schematic gate failed: "+board.report);
        auto input=load_board_inputs(paths,authored.circuits,link,extract_netlist(board.root_path,schematic.extraction));
        input.floorplan.sheet_index=index;
        const auto result=options.command=="w12-bound"?run_w12_bound(std::move(input),argument,selected):
            run_w12_stageprobe(std::move(input),argument,selected,options.conservative_only);
        std::cout<<result.output;return 0;
    }
    const auto som = options.som.empty() ? paths.som_schematic : options.som;
    if (options.command == "build") {
        if (options.subsystems.size()!=1) throw ProjectError("build requires exactly one registered subsystem name");
        if (!open_part_catalog((paths.repository_root/"native/catalog.bin").string()))
            throw ProjectError("cannot open native part catalog");
        ProjectAuthoringInput input;input.project_root=paths.project_root;
        input.context=make_authoring_context(paths.repository_root);
        const auto circuit=author_project_subsystem(paths.project_root.filename().string(),options.subsystems.front(),input);
        struct Scratch {fs::path path;~Scratch(){if(!path.empty()){std::error_code ignored;fs::remove_all(path,ignored);}}} scratch;
        auto output=options.output;
        if(output.empty()){
            auto pattern=(fs::temp_directory_path()/"schgen-build-XXXXXX").string();
            const auto created=::mkdtemp(pattern.data());if(!created)throw ProjectError("cannot create subsystem build scratch");
            scratch.path=created;output=scratch.path;
        }
        SymbolLibrary library(paths.repository_root);SubsystemBuildOptions build;
        build.no_render=options.no_render;build.extraction.kicad_cli=options.kicad_cli;
        const auto result=build_subsystem_sheet(circuit,library,output,build);
        std::cout<<result.report;return result.ok()?0:1;
    }
    if (options.command == "board") {
        if (!options.subsystems.empty()) throw ProjectError("board requires the complete project; subsystem selection is not supported");
        if (!open_part_catalog((paths.repository_root / "native/catalog.bin").string()))
            throw ProjectError("cannot open native part catalog");
        BoardPipelineOptions build;
        build.output_root = options.output;
        build.no_render = options.no_render;
        build.timing = options.timing;
        build.native_policy = true;
        build.extraction.kicad_cli = options.kicad_cli;
        const auto result = run_board_pipeline(paths, build);
        std::cout << result.report();
        return result.exit_code();
    }
    if (options.command == "model3d-check") {
        if (!options.subsystems.empty()) throw ProjectError("model3d-check takes no subsystem names");
        const auto directory = options.output.empty() ? paths.reports_dir : options.output;
        const auto result = run_model3d(paths.parts_dir, paths.project_root, directory);
        std::cout << result.line() << '\n';
        return result.ok ? 0 : 1;
    }
    if (options.command == "render3d" || options.command == "board-step") {
        if (!options.subsystems.empty()) throw ProjectError(options.command + " takes no subsystem names");
        const auto board = options.pcb.empty() ? paths.project_root / "Zynq_Carrier.kicad_pcb" : options.pcb;
        Render3dOptions render_options;
        render_options.kicad_cli = options.kicad_cli;
        if (options.command == "board-step") {
            if (options.output.empty()) throw ProjectError("board-step requires --output FILE");
            export_board_step(board, options.output, render_options);
            std::cout << "STEP: " << options.output.string() << '\n';
            return 0;
        }
        const auto directory = options.output.empty() ? paths.project_root / "renders" : options.output;
        const auto result = render_board_3d(board, directory, render_options);
        for (const auto& failure : result.failures)
            std::cerr << failure.view << ": " << failure.diagnostic << '\n';
        if (result.ok()) std::cout << result.summary() << '\n';
        return result.ok() ? 0 : 1;
    }
    if (options.command == "pcb-drc") {
        if (!options.subsystems.empty()) throw ProjectError("pcb-drc takes no subsystem names");
        const auto board = options.pcb.empty() ? paths.project_root / "Zynq_Carrier.kicad_pcb" : options.pcb;
        const auto result = run_pcb_drc(board);
        const auto errors = result.n_errors ? *result.n_errors :
            run_pcb_drc(board, std::chrono::minutes{5}, false).n_violations;
        std::string report = "PCB DRC: " + std::to_string(errors) + " errors, " +
            std::to_string(result.n_violations) + " total findings, " +
            std::to_string(result.n_unconnected) + " unconnected (unrouted)\n";
        for (const auto& [type, count] : result.by_type)
            report += "  " + type + ": " + std::to_string(count) + "\n";
        std::cout << report;
        if (!options.output.empty()) publish_text(options.output, report);
        return errors ? 1 : 0;
    }
    if (options.command == "som-interface") {
        if (!options.subsystems.empty()) throw std::runtime_error("som-interface takes no subsystem names");
        const auto output = options.output.empty() ? paths.som_interface_file : options.output;
        (void)refs(options.refs);
        std::cout << write_som_interface(som, options.refs, output, {options.kicad_cli});
        return 0;
    }
    if (options.command == "devicetree") {
        if (!options.subsystems.empty()) throw std::runtime_error("devicetree takes no subsystem names");
        const auto jrefs = refs(options.refs);
        const auto live = extract_som_zynq(som, "U2", jrefs, {options.kicad_cli});
        const auto input = load_devicetree_input(paths.repository_root, paths.project_root,
                                                live, options.contract, jrefs);
        const auto result = generate_devicetree(input);
        const auto output = options.output.empty() ? paths.project_root / "firmware/carrier_pl.dtsi"
                                                   : options.output;
        publish_text(output, result.text);
        std::cout << "DEVICETREE: " << output.string() << " (" << result.mio_rows.size() << " MIO rows)\n";
        return 0;
    }
    if (options.command == "selftest") {
        std::vector<SelftestSheetInput> inputs;
        if (options.subsystems.empty()) inputs.push_back({selftest_rc_fixture(), "m1_rc", "m1_rc"});
        const auto selected = load_project_circuits(paths, options.subsystems.empty()
            ? std::vector<std::string>{"uart_bridge"} : options.subsystems);
        for (const auto& circuit : selected)
            inputs.push_back({circuit.circuit, circuit.path.string(), circuit.name});
        FootprintResolutionOptions fp;
        fp.parts_dir = paths.parts_dir;
        fp.library_tables = {paths.repository_root / "som/fp-lib-table"};
        for (const auto* root : {"/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints",
                                "/usr/share/kicad/footprints", "/usr/local/share/kicad/footprints"})
            if (fs::is_directory(root)) { fp.kicad_footprint_root = root; break; }
        const auto resistor = resolve_footprint("Resistor_SMD:R_0603_1608Metric",
            load_footprint_library_tables(fp), fp);
        if (!resistor) throw std::runtime_error("selftest requires the real R_0603_1608Metric footprint");
        std::ifstream source(*resistor, std::ios::binary);
        if (!source) throw std::runtime_error("cannot read selftest footprint " + resistor->string());
        const std::string bytes((std::istreambuf_iterator<char>(source)), std::istreambuf_iterator<char>());
        const auto executable = find_executable(argv[0]);
        if (!executable) throw std::runtime_error("cannot resolve selftest worker executable");
        SelftestFullOptions run;
        run.keep = options.keep;
        run.extraction.kicad_cli = options.kicad_cli;
        run.worker_command = {fs::absolute(*executable).string(), "selftest-worker"};
        run.progress = [](const std::string& text) { std::cout << text << std::flush; };
        SymbolLibrary library(paths.repository_root);
        const auto result = run_full_selftest(inputs,
            selftest_model_fixtures(pcb_check_footprint(resistor->string(), bytes)), library, run);
        if (!options.output.empty()) publish_text(options.output, result.report);
        return result.exit_code();
    }
    if (options.command == "assembly" || options.command == "ratsnest") {
        if (!options.subsystems.empty()) throw ProjectError(options.command + " requires the complete project");
        const auto stage = prepare_board_pcb(paths, {options.kicad_cli});
        const auto directory = options.output.empty() ? paths.project_root : options.output;
        if (options.command == "ratsnest") {
            const auto result = run_ratsnest_documents(stage.placement.model, directory);
            std::cout << ratsnest_document_summary(result, directory);
            return 0;
        }
        const auto result = run_assembly_documents(stage.placement.model,
            analyze_power(stage.circuits), stage.inputs.floorplan.project.name,
            directory / "manufacturing/ASSEMBLY.md", directory / "renders/assembly",
            pcb_emit_policy(stage.inputs.floorplan.project));
        const auto verdict = assembly_verdict(result, directory);
        std::cout << verdict.second << '\n';
        return verdict.first ? 0 : 1;
    }
    if (options.command == "fab-profile") {
        if (!options.subsystems.empty()) throw ProjectError("fab-profile requires the emitted project board");
        const auto reports = options.output.empty() ? paths.reports_dir : options.output;
        const auto result = run_manufacturing_fab(reports, paths.project_root / "Zynq_Carrier.kicad_pcb",
            paths.project_root / "manufacturing/Zynq_Carrier_pcb.kicad_dru", paths.project_root / "Zynq_Carrier.kicad_pro");
        std::cout << result.report() << '\n';
        return result.ok ? 0 : 1;
    }
    if (options.command == "pcb-stage") {
        if (options.output.empty()) throw ProjectError("pcb-stage requires --output DIRECTORY");
        if (!options.subsystems.empty()) throw ProjectError("pcb-stage requires the complete project, not selected sheets");
        const auto stage = prepare_board_pcb(paths, {options.kicad_cli});
        publish_board_pcb(stage, options.output);
        for (const auto& diagnostic : stage.emission.diagnostics) std::cout << diagnostic << '\n';
        std::cout << "PCB STAGE: constructed " << stage.placement.model.insts.size()
                  << " footprints -> " << options.output.string()
                  << " (construction only; independent board gates must still run)\n";
        return 0;
    }
    const auto circuits = options.subsystems.empty() ? load_project_circuits(paths)
                        : load_project_circuits(paths, options.subsystems);
    std::vector<CircuitSheetIr> sheets;
    sheets.reserve(circuits.size());
    for (const auto& circuit : circuits) sheets.push_back(circuit.circuit);
    if (options.command == "gallery") {
        if (!options.subsystems.empty()) throw ProjectError("gallery requires the complete project");
        const auto input = load_gallery_input(paths, circuits);
        const auto changed = write_gallery(input);
        std::cout << gallery_summary(input, changed) << '\n';
        return 0;
    }
    if (options.command == "preflight") {
        const auto result = assess_procurement(procurement_inventory(circuits), live_procurement_provider(),
            options.quantity, options.minimum_stock, options.allow_missing);
        if (!options.output.empty()) publish_text(options.output, result.report);
        std::cout << result.report;
        return result.ok ? 0 : 1;
    }
    if (options.command == "manifest") {
        const auto pins = stm32_pin_map(extract_som_zynq(paths.som_schematic, "U9",
            {"J1", "J2", "J3"}, {options.kicad_cli}), load_som_interface(paths.som_interface_file));
        const auto input = prepare_manufacturing_manifest(circuits, pins);
        const auto destination = options.output.empty() ? paths.manifest_file : options.output;
        run_manufacturing_manifest(input, paths.project_root, destination);
        std::cout << "MANIFEST: " << destination.string() << '\n';
        return 0;
    }
    if (options.command == "si-constraints") {
        const auto directory = options.output.empty() ? paths.project_root : options.output;
        const auto result = run_si_constraints(circuits, paths.project_root / "research/si_spec.json",
            directory / "manufacturing/Zynq_Carrier_pcb.kicad_dru", directory / "manufacturing/SI_CONSTRAINTS.md");
        std::cout << result.verdict.summary() << '\n';
        return result.verdict.ok ? 0 : 1;
    }
    if(options.command=="firmware" || options.command=="manual" || options.command=="scfw" ||
       options.command=="testplan" || options.command=="power-sequence") {
        FirmwareDocsInput in;in.sheets=circuits;in.firmware_sources=firmware_sources(paths);
        std::vector<std::string> missing;
        if(options.command=="manual")missing=manual_missing_requirements(in);
        if(options.command=="scfw")missing=scfw_missing_requirements(in);
        if(!missing.empty()) {
            std::cout<<options.command<<": SKIP — project missing";
            for(const auto& name:missing)std::cout<<' '<<name;
            std::cout<<'\n';return 1;
        }
        if(options.command=="firmware" || options.command=="manual" || options.command=="scfw")
            in.stm32=stm32_pin_map(extract_som_zynq(paths.som_schematic,"U9",{"J1","J2","J3"},{options.kicad_cli}),
                                  load_som_interface(paths.som_interface_file));
        if(options.command=="scfw") {
            const auto artifacts=render_scfw(in);
            const auto directory=options.output.empty()?paths.project_root/"firmware/sc":options.output;
            for(const auto& artifact:artifacts)publish_text(directory/artifact.path,artifact.text);
            std::cout<<"SCFW SCAFFOLD: "<<directory.string()<<" ("<<artifacts.size()<<" files)\n";return 0;
        }
        std::string text;fs::path default_path;
        if(options.command=="firmware") {text=render_firmware_contract(in);default_path="firmware/zynq_carrier_contract.h";}
        else if(options.command=="manual") {text=render_bringup_manual(in);default_path="docs/BRINGUP.md";}
        else if(options.command=="power-sequence") {
            const auto power=analyze_power(circuits);
            text=render_power_sequence_svg(build_power_sequence(circuits,power),power.ok());default_path="docs/power_sequence.svg";
        } else {
            ProjectStrings probes;
            for(const auto& [net,locations]:check_testpoint_coverage(sheets).have) {
                std::string value;for(const auto& location:locations){if(!value.empty())value+=", ";value+=location;}
                probes.emplace_back(net,value);
            }
            text=render_test_plan(in,extract_spice_checks(circuits),probes);default_path="docs/TEST_PLAN.md";
        }
        const auto output=options.output.empty()?paths.project_root/default_path:options.output;
        publish_text(output,text);std::cout<<options.command<<": "<<output.string()<<'\n';return 0;
    }
    if (options.command == "bom-values" || options.command == "footprint-pads" ||
        options.command == "pin-completeness" || options.command == "symbol-law" || options.command == "spice") {
        std::string report;bool ok=false;
        const auto data=paths.repository_root/"schgen/verify/data";
        if(options.command=="bom-values") {
            const auto r=check_bom_values(circuits,load_bom_value_catalog(data/"lcsc_values.json"));
            report=r.report();ok=r.ok;
        } else if(options.command=="spice") {
            auto r=extract_spice_checks(circuits);SpiceRunOptions run;run.allow_ngspice=!options.no_ngspice;
            run_ngspice_crosschecks(r,run);report=spice_report(r,ngspice_available().has_value());ok=r.ok();
        } else {
            SymbolLibrary library(paths.repository_root);
            if(options.command=="pin-completeness") {
                const auto r=check_pin_completeness(circuits,library,load_nc_allowlist(data/"nc_allowlist.json"));
                report=r.report();ok=r.ok;
            } else if(options.command=="symbol-law") {
                const auto r=check_symbol_law(sheets,library);report=r.summary();ok=r.ok();
            } else {
                FootprintResolutionOptions fp;fp.parts_dir=paths.repository_root/"parts";
                fp.library_tables={paths.repository_root/"som/fp-lib-table"};
                fp.aliases={{"Capacitor_SMD:C_1206_3225Metric","Capacitor_SMD:C_1206_3216Metric"}};
                for(const auto* root:{"/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints","/usr/share/kicad/footprints","/usr/local/share/kicad/footprints"})
                    if(fs::is_directory(root)){fp.kicad_footprint_root=root;break;}
                const auto r=check_footprint_pads(circuits,library,fp);report=r.report();ok=r.ok;
            }
        }
        if(!options.output.empty())publish_text(options.output,report+"\n");
        std::cout<<report<<'\n';return ok?0:1;
    }
    if (options.command == "powertree" || options.command == "thermal" || options.command == "part-rules") {
        const auto power = analyze_power(circuits);
        std::string report;
        bool ok = false;
        if (options.command == "powertree") {
            report = power_report(power); ok = power.ok();
        } else if (options.command == "part-rules") {
            const auto result = analyze_part_rules(circuits,power);
            report = part_rules_report(result); ok = result.ok();
        } else {
            const auto pcb = options.pcb.empty() ? paths.project_root / "Zynq_Carrier.kicad_pcb" : options.pcb;
            std::optional<ThermalCopper> copper;
            if (fs::exists(pcb)) copper = scan_thermal_copper(pcb);
            std::string source;
            if (copper) {
                const auto relative = fs::weakly_canonical(pcb).lexically_relative(paths.repository_root);
                source = !relative.empty() && *relative.begin() != ".." ? relative.string() : pcb.string();
            }
            const auto result = analyze_thermal(circuits,power,copper?&*copper:nullptr,source);
            report = thermal_report(result); ok = result.ok();
        }
        if (!options.output.empty()) publish_text(options.output,report+"\n");
        std::cout << report << '\n';
        return ok ? 0 : 1;
    }
    if (options.command == "constraints") {
        const auto directory = options.output.empty() ? paths.project_root / "manufacturing" : options.output;
        const auto result = write_layout_constraints(circuits, paths.project_root / "research/si_spec.json", directory);
        std::cout << "LAYOUT CONSTRAINTS: " << result.port_count << " ports -> " << directory.string() << '\n';
        return 0;
    }
    if (options.command == "board-schematic") {
        // A schematic-stage command, not an alias for the complete board
        // pipeline: PCB, manufacturing and model gates remain separate.
        if (options.output.empty())
            throw std::runtime_error("board-schematic requires --output DIRECTORY (schematic stage only)");
        const auto index = load_sheet_index(paths);
        std::vector<BoardSheetInput> input;
        for (const auto& c : circuits) {
            const auto band = std::find_if(index.begin(), index.end(),
                [&](const auto& item) { return item.first == c.name; });
            if (band == index.end())
                throw std::runtime_error("missing persistent sheet-index band for " + c.name);
            input.push_back({c.circuit, band->second, std::nullopt});
        }
        SymbolLibrary library(paths.repository_root);
        BoardSchematicOptions build;
        build.root_name = "Zynq_Carrier";
        build.sheet_subdir = "schematic";
        build.reports_dir = options.output / "reports";
        build.extraction.kicad_cli = options.kicad_cli;
        const auto result = build_board_schematic(input, library, options.output, build);
        std::cout << result.report << '\n';
        std::cout << "BOARD SCHEMATIC: " << (result.ok() ? "PASS" : "FAIL")
                  << " (schematic stage only; " << input.size() << " sheets)\n";
        return result.ok() ? 0 : 1;
    }
    if (options.command == "design-rules" || options.command == "testpoints") {
        std::string report;
        bool ok;
        if (options.command == "design-rules") {
            SymbolLibrary library(paths.repository_root);
            const auto result = check_design_rules(sheets,
                [&](const std::string& id) -> const SymbolDef& { return library.get(id); });
            report = result.report();
            ok = result.ok();
        } else {
            const auto result = check_testpoint_coverage(sheets);
            report = result.report();
            ok = result.ok();
        }
        if (!options.output.empty()) publish_text(options.output, report + "\n");
        std::cout << report << '\n';
        return ok ? 0 : 1;
    }
    if (options.command == "circuit-check") {
        SymbolLibrary library(paths.repository_root);
        bool ok = true;
        for (const auto& sheet : sheets) {
            const auto result = check_circuit_electrical(sheet, library);
            std::cout << sheet.name << ": " << result.summary() << '\n';
            ok = result.ok() && ok;
        }
        return ok ? 0 : 1;
    }
    if (options.command == "link" || options.command == "diagram") {
        SymbolLibrary library(paths.repository_root);
        for (const auto& sheet : sheets) validate_circuit(sheet, library);
        const auto contract = options.contract.empty() ? paths.som_interface_file : options.contract;
        const auto contract_json = parse_json_file(contract.string());
        const auto result = link_sheets(sheets, contract_json,
            parse_json_file((paths.project_root / "som_mapping.json").string()));
        if (options.command == "diagram") {
            const auto output = options.output.empty() ? paths.project_root / "docs/block_diagram.svg" : options.output;
            write_block_diagram(result, link_som_nets_from_json(contract_json), output);
            std::cout << "DIAGRAM: " << output.string() << '\n';
            return result.ok() ? 0 : 1;
        }
        const auto report = result.report();
        if (!options.output.empty()) publish_text(options.output, report + "\n");
        std::cout << report << '\n';
        return result.ok() ? 0 : 1;
    }
    if (options.command == "project-check") {
        std::size_t parts = 0, nets = 0;
        for (const auto& sheet : sheets) { parts += sheet.parts.size(); nets += sheet.nets.size(); }
        std::cout << "PROJECT: PASS " << config.name << " (" << sheets.size()
                  << " circuits, " << parts << " parts, " << nets << " nets; native JSON validation)\n";
        return 0;
    }
    if (options.command == "bom") {
        const auto bom = generate_bom(sheets, options.qualified_refs);
        const auto output = options.output.empty() ? fs::current_path() / "bom_jlc.csv" : options.output;
        publish_text(output, bom.csv);
        std::cout << "BOM written: " << output.string() << " (" << bom.rows.size() << " line items)\n";
        if (!bom.missing_lcsc.empty()) {
            std::cout << "MISSING LCSC (" << bom.missing_lcsc.size() << "):\n";
            for (const auto& missing : bom.missing_lcsc) std::cout << "  " << missing << '\n';
        }
        return bom.missing_lcsc.empty() || options.allow_missing ? 0 : 1;
    }
    XdcInput live_input;
    live_input.refs = refs(options.refs);
    const auto live = extract_som_zynq(som, "U2", live_input.refs, {options.kicad_cli});
    apply_som_to_xdc(live_input, live);
    const auto input = load_project_xdc_input(paths.repository_root, paths.project_root,
        sheets, std::move(live_input), som, options.contract);
    const auto xdc = generate_xdc(input);
    const auto fpga_dir = options.command == "fpga" && !options.output.empty()
                        ? options.output : paths.fpga_dir;
    const auto xdc_path = options.command == "xdc" && !options.output.empty() ? options.output
                        : !options.xdc.empty() ? options.xdc : fpga_dir / "Zynq_Carrier_pins.xdc";
    const auto vivado_path = options.command == "vivado" && !options.output.empty() ? options.output
                           : fpga_dir / "create_project.tcl";
    std::string vivado;
    if (options.command != "xdc") {
        const auto relative = fs::weakly_canonical(xdc_path).lexically_relative(
            fs::weakly_canonical(vivado_path.parent_path()));
        vivado = render_vivado(xdc, input.device, input.zynq_ref,
                               relative.generic_string(), input.refs);
    }
    // Finish every validation/render before publishing any member of the batch.
    if (options.command != "vivado") publish_text(xdc_path, xdc.text);
    if (options.command != "xdc") publish_text(vivado_path, vivado);
    for (const auto& check : xdc.checks) std::cout << "  check: " << check << '\n';
    if (options.command != "vivado")
        std::cout << "XDC: " << xdc_path.string() << " (" << xdc.entries.size() << " pins)\n";
    if (options.command != "xdc") std::cout << "VIVADO: " << vivado_path.string() << "\n";
    return 0;
}
}
