#include "schgen/project_cli.hpp"

#include "schgen/bom.hpp"
#include "schgen/board_schematic.hpp"
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

#include <algorithm>
#include <filesystem>
#include <iostream>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace schgen {
namespace {
namespace fs = std::filesystem;
struct Options {
    std::string command, refs = "J1,J2,J3", kicad_cli = "kicad-cli";
    fs::path repository = fs::current_path(), som, contract, output, xdc, pcb;
    std::optional<fs::path> project;
    std::vector<std::string> subsystems;
    bool allow_missing = false, qualified_refs = false, no_ngspice = false;
};
const std::set<std::string> commands{"project-check", "circuit-check", "som-interface", "xdc", "vivado", "fpga", "bom", "link", "devicetree", "design-rules", "testpoints", "board-schematic", "constraints", "powertree", "thermal", "part-rules", "bom-values", "footprint-pads", "pin-completeness", "symbol-law", "spice", "firmware", "manual", "scfw", "testplan", "power-sequence"};
Options parse(int argc, char** argv) {
    Options out;
    std::set<std::string> seen;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (commands.count(arg) && out.command.empty()) { out.command = arg; continue; }
        if (arg == "--allow-missing" || arg == "--qualified-refs" || arg == "--no-ngspice") {
            if (!seen.insert(arg).second) throw std::runtime_error("duplicate option " + arg);
            if (arg == "--allow-missing") out.allow_missing = true;
            else if (arg == "--qualified-refs") out.qualified_refs = true;
            else out.no_ngspice = true;
            continue;
        }
        if (arg == "--repo" || arg == "--project" || arg == "--som" ||
            arg == "--contract" || arg == "--output" || arg == "-o" ||
            arg == "--xdc" || arg == "--refs" || arg == "--kicad-cli" || arg == "--pcb" ||
            arg == "--subsystem") {
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
            else out.subsystems.push_back(value);
        } else if (!arg.empty() && arg[0] != '-' && !out.command.empty()) {
            out.subsystems.push_back(arg);
        } else throw std::runtime_error("unknown project command or option: " + arg);
    }
    if (out.command.empty()) throw std::runtime_error("missing project command; use --help");
    std::set<std::string> allowed{"--repo", "--project"};
    const bool check_only = out.command == "project-check" || out.command == "circuit-check";
    if (!check_only) allowed.insert("--output");
    if (out.command == "bom") {
        allowed.insert("--allow-missing"); allowed.insert("--qualified-refs");
    } else if (out.command == "link") {
        allowed.insert("--contract");
    } else if (out.command == "board-schematic") {
        allowed.insert("--kicad-cli");
    } else if (out.command == "thermal" || out.command == "powertree" || out.command == "part-rules") {
        if (out.command == "thermal") allowed.insert("--pcb");
    } else if (out.command == "spice") {
        allowed.insert("--no-ngspice");
    } else if (out.command == "firmware" || out.command == "manual" || out.command == "scfw") {
        allowed.insert("--kicad-cli");
    } else if (out.command == "testplan" || out.command == "power-sequence") {
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
    if (!commands.count(first) && first != "--repo" && first != "--project") return std::nullopt;
    const auto options = parse(argc, argv);
    const auto paths = resolve_project_paths(options.repository, options.project);
    const auto config = load_project_config(paths);
    const auto som = options.som.empty() ? paths.som_schematic : options.som;
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
    const auto circuits = options.subsystems.empty() ? load_project_circuits(paths)
                        : load_project_circuits(paths, options.subsystems);
    std::vector<CircuitSheetIr> sheets;
    sheets.reserve(circuits.size());
    for (const auto& circuit : circuits) sheets.push_back(circuit.circuit);
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
    if (options.command == "link") {
        SymbolLibrary library(paths.repository_root);
        for (const auto& sheet : sheets) validate_circuit(sheet, library);
        const auto contract = options.contract.empty() ? paths.som_interface_file : options.contract;
        const auto result = link_sheets(sheets, parse_json_file(contract.string()),
            parse_json_file((paths.project_root / "som_mapping.json").string()));
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
