#include "schgen/pcb_verification.hpp"

namespace schgen {
bool PcbVerificationResult::ok() const {
    return complete && ratsnest.ok && mechanical.ok && connector_models.ok && connector_spacing.ok &&
        refdes.ok && placement.ok() && fanout.ok && return_stitch.ok && escape_lanes.ok;
}
PcbVerificationResult verify_pcb_geometry(const BoardPcbStage& stage,
        const PcbEmittedBoard& emitted, std::optional<int> baseline) {
    if (!emitted.exists) throw ProjectError("PCB verification requires the emitted board");
    const auto& model = stage.placement.model;
    const auto& input = stage.inputs;
    const PcbCheckInput prepared(model);
    PcbVerificationResult out;
    out.nets = ratsnest_net_pad_positions(model);
    out.edges = ratsnest_mst(out.nets);
    out.ratsnest = check_ratsnest(prepared, &out.nets, &out.edges);
    out.mechanical = check_placement_mech(prepared);
    const auto policy = pcb_emit_policy(input.floorplan.project);
    const std::map<std::string,std::string> faces(policy.connector_mating_faces.begin(), policy.connector_mating_faces.end());
    out.connector_models = check_connector_models(model, faces);
    out.connector_spacing = check_connector_spacing(prepared);
    out.refdes = check_refdes_overlap(emitted.document, true);
    out.placement = check_pcb_placement_gates(prepared, pcb_placement_gate_policy(input),
        pcb_final_compose_index(input, model), pcb_compose_evidence(model), &out.nets, &out.edges);
    out.fanout = check_fanout(prepared, baseline);
    out.return_path = check_return_path(input.som_interface, input.return_path_footprints);
    std::map<std::string,ReturnStitchClass> triage;
    for (const auto& violation : out.return_path.violations) {
        const auto classification = classify_pcb_escape_signal(violation.net, input.function_map);
        triage.emplace(violation.net, ReturnStitchClass{classification.rank(), classification.klass, classification.function});
    }
    out.return_stitch = check_return_stitch(prepared, out.return_path, triage, input.interface_bytes, &emitted);
    out.escape_lanes = check_escape_lanes(model,
        pcb_escape_population_from_json(input.floorplan.project.escape), input.interface_bytes);
    out.complete = true;
    return out;
}
}
