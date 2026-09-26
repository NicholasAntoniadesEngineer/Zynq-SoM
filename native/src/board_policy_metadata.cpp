#include "schgen/board_policy.hpp"

namespace schgen {
ManufacturingPipelineInput native_board_pipeline_metadata(){
    ManufacturingPipelineInput out;
    // Reviewed against Placer::seed/build/checkpoint, not discovered from events.
    out.stages={
        {"zone_pack","board","Native template feasibility, per-zone fanout reservation and shape registration; infeasible contracts fail","Construct local two-sided zone geometry",true,false},
        {"plan_lattice","board","Occupancy separation, pair recheck, composition legalizer and LAW-5 estimate","Search the outline and place subsystem blocks",true,false},
        {"shape_bind","board","Chosen shape index must exist; mirror documents and side membership rebind without moving poses","Apply the plan's registered shape choices",false,false},
        {"step3_emission","board","Exact plan origin plus zone offsets; emitted geometry is independently verified later","Seed board-frame MH, SoM, zone and decoupling poses",true,true},
        {"l4_pull","board","Bottom/THT/corridor collision set, foreign D13 floors, board margin and dispersion cap","Rigid SoM-ward pull of bottom passive clusters",true,true},
        {"edge_seat","board","Connector pad-flush axis only; final mechanical gate judges the emitted result","Seat off-board connectors at the board edge",true,true},
        {"breathe","board","Every snapped commit rechecks collision and leash; dispersion failure reverts the sheet","Spread starved movable IC groups into free space",true,true},
        {"refit_facing","board","Final placement-flow, contract and DRC gates independently check the rigid turn","Turn a downstream contracted zone only when facing requires it",true,true},
        {"reorder","board","Identical footprint/rotation/side slot permutation; strict crossing-count improvement","Uncross interchangeable parts without changing occupied geometry",true,true},
        {"corridor_eviction","board","Post-gridified corridor collision, bottom/THT/edge and foreign D13 checks; counted failures","Evict bottom strays from the final DF40 stitch corridors",true,true},
        {"instantiate","board","Always-on checkpoint rejects movement of any existing board-frame part","Project frozen poses into footprint instances",false,true},
        {"emission_frame","page","Origin translation plus registered fixed-part grid; same grid used for corridor prediction","Establish the emitted page-frame snapshot including fiducials",true,true},
        {"escape_copper","page","Always-on checkpoint forbids footprint movement; final return-stitch/escape gates","Derive return stitching and lane copper from frozen footprints",false,true}};
    // These ten labels/stages are exact registry keys. Descriptions describe the
    // actual native producers, not historical recorded board populations.
    out.fallbacks={
        {"legalize_only_compaction","plan_lattice","Compact placement broke a pair floor; retain the rechecked legalize-only candidate. Count each affected compact-pack invocation."},
        {"seat_node_budget","zone_pack","Template DFS exhausted its node budget; that pad is infeasible and the widening search may retry."},
        {"cand_cap_truncated","zone_pack","Ranked candidate list exceeded its cap; discard the tail and count this truncating generation call."},
        {"thermal_via_lattice","emission","A preferred thermal via site was blocked; a checked lattice candidate supplied the via. Count each such via."},
        {"bottom_variant_contract_reject","zone_pack","An eligible bottom variant failed its mirrored contract or required lifting a load-bearing contract member; do not offer that shape."},
        {"corridor_evict_moved","corridor_eviction","A stray was moved to a legal exit from a final-frame DF40 corridor. Count moved parts."},
        {"corridor_stray_unmovable","corridor_eviction","A corridor stray had no legal exit and remained; the escape solver must prove coexistence or fail."},
        {"punch_free_plan_rejected","plan_lattice","The free-punch candidate was infeasible or failed strict area/estimate improvement; retain the conservative plan and its fallback snapshot."},
        {"interior_reseat_retry","plan_lattice","Bounded eviction and reseating found a legal interior placement after greedy seating failed. Count successful retry episodes across all candidates."},
        {"assembly_generation_failed","assembly_docs","Current-board assembly generation threw; the pipeline must fail and must not treat an older document as current evidence."}};
    NativeQuantizations q;register_native_quantizations(q);
    for(const auto& d:q.declarations())out.quantization.push_back({d.name,d.value,d.proof_class,d.basis});
    return out;
}
std::vector<CppAuditSource> native_board_policy_audit_sources(){
    // Deliberate, repository-relative scope. No regex discovery, scanner-output
    // registration, directory allowlist or baseline suppression is used here.
    std::vector<CppAuditSource> out;
    for(const auto* name:{
        "quantize.cpp","native_audit_quantize.cpp","precision_ops.cpp","occupancy_precision.cpp","legalize_precision.cpp","stage_precision.cpp",
        "floorplan_internal.hpp","floorplan_geometry.cpp","floorplan_cross.cpp",
        "floorplan_pack.cpp","floorplan_compose.cpp","floorplan_build.cpp",
        "floorplan_notes.cpp","floorplan_svg.cpp","floorplan_md.cpp","floorplan_ledger.cpp",
        "pcb_stage_internal.hpp","pcb_stage_geometry.cpp","pcb_stage_search.cpp",
        "pcb_stage_power.cpp","pcb_stage_zone.cpp","pcb_placement_internal.hpp",
        "pcb_placement_inputs.cpp","pcb_placement_pack.cpp","pcb_placement_variants.cpp",
        "pcb_placement_zones.cpp","pcb_placement_model.cpp","pcb_placement_moves.cpp",
        "pcb_placement_breathe.cpp","pcb_placement_build.cpp","pcb_escape_internal.hpp",
        "pcb_escape_copper.cpp","pcb_escape_plan.cpp","pcb_escape_model.cpp","pcb_escape_triage.cpp",
        "pcb_embed.cpp","pcb_emit.cpp","pcb_project.cpp","pcb_silk.cpp","legalize.cpp",
        "occupancy.cpp","pack.cpp","pack_edges.cpp","pack_anchor.cpp","pack_refine.cpp",
        "ratsnest_gate.cpp","accurate_norm.hpp","pcb_checks_placement.cpp"})out.push_back({std::string("native/src/")+name});
    for(const auto* name:{"floorplan.hpp","ratsnest_gate.hpp","pack.hpp","occupancy.hpp",
        "legalize.hpp","pack_edges.hpp","pack_anchor.hpp","pack_refine.hpp","pcb_stage_templates.hpp",
        "quantize.hpp","board_decision_policy.hpp"})
        out.push_back({std::string("native/include/schgen/")+name});
    return out;
}
}
