#include "schgen/board_pcb.hpp"
#include "schgen/atomic_file.hpp"
#include "schgen/validation.hpp"

namespace schgen {
BoardPcbStage prepare_board_pcb(const ProjectPaths& paths,
        const NetlistExtractOptions& extraction, const BoardInputOptions& options) {
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
    const auto nets = extract_netlist(paths.project_root / "Zynq_Carrier.kicad_sch", extraction);
    BoardPcbStage out;
    out.inputs = load_board_inputs(paths, circuits, link, nets, options);
    out.placement = build_pcb_model(out.inputs);
    out.emission = render_pcb(out.placement.model, pcb_emit_policy(out.inputs.floorplan.project));
    return out;
}
void publish_board_pcb(const BoardPcbStage& stage, const std::filesystem::path& directory) {
    if (directory.empty()) throw ProjectError("PCB stage requires an output directory");
    const auto policy = pcb_emit_policy(stage.inputs.floorplan.project);
    const auto project_path = directory / "Zynq_Carrier.kicad_pro";
    std::optional<PcbProjectDocument> existing;
    if (std::filesystem::exists(project_path)) existing = read_pcb_project(project_path);
    const auto project = render_pcb_project(stage.placement.model, project_path.filename().string(),
        existing ? &*existing : nullptr, policy);
    const auto rules = render_pcb_design_rules(stage.placement.model, policy);
    const auto publish = [&](const std::string& name, const std::string& text) {
        write_atomic_file((directory / name).string(), {text.begin(), text.end()});
    };
    publish("Zynq_Carrier.kicad_pcb", stage.emission.pcb);
    publish("Zynq_Carrier.kicad_pro", project);
    publish("Zynq_Carrier.kicad_dru", rules);
    write_floorplan_documents(stage.placement.floorplan.documents, directory / "manufacturing");
}
}
