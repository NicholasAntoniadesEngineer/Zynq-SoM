#include "schgen/board_pcb.hpp"
#include "schgen/board_schematic.hpp"
#include "schgen/atomic_file.hpp"
#include "schgen/validation.hpp"

namespace schgen {
void validate_board_input_connectivity(const std::vector<ProjectCircuit>& circuits,
        const SheetIndex& index, const KicadNetlist& extracted) {
    using Pin=std::pair<std::string,std::string>;
    using Net=std::pair<std::string,std::string>;
    const auto fail=[](const std::string& why) {
        throw ProjectError("PCB input connectivity: "+why);
    };
    std::map<std::string,int> bands;
    std::set<int> used_bands;
    for(const auto& [sheet,band]:index)
        if(!bands.emplace(sheet,band).second||!used_bands.insert(band).second)
            fail("duplicate sheet/index band");
    std::map<Pin,Net> expected;
    std::set<std::string> sheets;
    for(const auto& sheet:circuits) {
        if(!sheets.insert(sheet.name).second||!bands.count(sheet.name))
            fail("duplicate or unindexed sheet "+sheet.name);
        for(const auto& net:sheet.circuit.nets) {
            const bool shared=net.net_class=="power"||net.net_class=="ground"||net.net_class=="port";
            const Net key{shared?"":sheet.name,net.name};
            for(const auto& pin:net.pins) {
                const Pin renamed{board_renamed_ref(pin.ref,bands.at(sheet.name),sheet.name),pin.pin};
                if(!expected.emplace(renamed,key).second)fail("duplicate authored pin "+renamed.first+"."+renamed.second);
            }
        }
    }
    std::map<Pin,std::string> actual;
    std::set<std::string> names;
    for(const auto& [name,pins]:extracted) {
        if(!names.insert(name).second)fail("duplicate extracted net "+name);
        if(name.empty()||name.rfind("unconnected-",0)==0)continue;
        for(const auto& pin:pins) {
            if(pin.ref.rfind("#",0)==0)continue; // KiCad-only power symbols/flags.
            const Pin key{pin.ref,pin.pin};
            if(!actual.emplace(key,name).second)fail("multiply-netted extracted pin "+pin.ref+"."+pin.pin);
            if(!expected.count(key))fail("unexpected connected pin "+pin.ref+"."+pin.pin);
        }
    }
    std::map<Net,std::string> forward;
    std::map<std::string,Net> reverse;
    for(const auto& [pin,key]:expected) {
        const auto found=actual.find(pin);
        if(found==actual.end())fail("missing connected pin "+pin.first+"."+pin.second);
        const auto& name=found->second;
        const auto [f,inserted]=forward.emplace(key,name);
        if(!inserted&&f->second!=name)fail("split authored net "+key.first+":"+key.second);
        const auto [r,new_net]=reverse.emplace(name,key);
        if(!new_net&&r->second!=key)fail("shorted authored nets on "+name);
        if(key.first.empty()&&normalize_netlist_name(name)!=key.second)
            fail("public net identity changed: "+key.second+" -> "+name);
    }
}
BoardPcbStage prepare_board_pcb(const ProjectPaths& paths,
        const NetlistExtractOptions& extraction, const BoardInputOptions& options,
        const std::filesystem::path& schematic) {
    const auto circuits = load_project_circuits(paths);
    SymbolLibrary library(paths.repository_root);
    std::vector<CircuitSheetIr> sheets;
    for (const auto& source : circuits) {
        validate_circuit(source.circuit, library);
        sheets.push_back(source.circuit);
    }
    const auto link = link_sheets(sheets, parse_json_file(paths.som_interface_file.string()),
        parse_json_file((paths.project_root / "som_mapping.json").string()));
    if (!link.ok()) throw ProjectError(link.report());
    const auto nets = extract_netlist(schematic.empty()?paths.project_root / "Zynq_Carrier.kicad_sch":schematic, extraction);
    validate_board_input_connectivity(circuits,load_sheet_index(paths),nets);
    BoardPcbStage out;
    out.circuits = circuits;
    out.inputs = load_board_inputs(paths, circuits, link, nets, options);
    out.placement = build_pcb_model(out.inputs);
    out.emission = render_pcb(out.placement.model, pcb_emit_policy(out.inputs.floorplan.project));
    return out;
}
void publish_board_pcb(const BoardPcbStage& stage, const std::filesystem::path& directory,
                       QuantizationCounts* counts) {
    if (directory.empty()) throw ProjectError("PCB stage requires an output directory");
    const auto policy = pcb_emit_policy(stage.inputs.floorplan.project);
    const auto project_path = directory / "Zynq_Carrier.kicad_pro";
    std::optional<PcbProjectDocument> existing;
    if (std::filesystem::exists(project_path)) existing = read_pcb_project(project_path);
    const auto project = render_pcb_project(stage.placement.model, project_path.filename().string(),
        existing ? &*existing : nullptr, policy, counts);
    const auto rules = render_pcb_design_rules(stage.placement.model, policy);
    const auto publish = [&](const std::string& name, const std::string& text) {
        write_atomic_file((directory / name).string(), {text.begin(), text.end()});
    };
    publish("Zynq_Carrier.kicad_pcb", stage.emission.pcb);
    publish("Zynq_Carrier.kicad_pro", project);
    publish("manufacturing/Zynq_Carrier_pcb.kicad_dru", rules);
    // Preserve the emitter's evidence in both pcb-stage and full board builds.
    // A fallback count alone does not identify the affected thermal geometry.
    std::string diagnostics = "PCB emission diagnostics (not a qualification verdict)\n";
    for (const auto& message : stage.emission.diagnostics) diagnostics += message + '\n';
    publish("reports/pcb_emission.txt", diagnostics);
    write_floorplan_documents(stage.placement.floorplan.documents, directory / "docs");
}
}
