#include "schgen/board_policy.hpp"
#include "schgen/board_decision_policy.hpp"
#include "schgen/experiment_observers.hpp"
#include "schgen/quantize.hpp"
#include "pcb_stage_internal.hpp"
#include "schgen/ratsnest_gate.hpp"
#include <cmath>
#include <sstream>

namespace schgen {
namespace {
JsonNode number(double value){
    if(!std::isfinite(value))throw ProjectError("native board policy: nonfinite live assumption");
    JsonNode out;out.kind=JsonKind::Number;out.number_value=value;return out;
}
struct Binding {const char* name;const char* symbol;};
// Explicit semantic review, never populated from a compiler census.
const std::vector<Binding> floor_bindings{
    {"edge_margin","edge_margin"},{"mh_corner_keepout","mh_corner"},
    {"edge_inset","edge_inset"},{"cable_neighbor_gap","cable_gap"},
    {"block_clearance","clear"},{"perimeter_keepout","perimeter"},
    {"som_halo","som_halo"},{"pack_efficiency","fill"},
    {"occ_top_mask","occ_top"},{"occ_bottom_mask","occ_bottom"},
    {"som_seat_band","som_seat_band"},{"som_occ_pad","som_pad"},
    {"som_decoupling_inset","dec_inset"},{"d13_min_subject_pins","min_subject_pins"},
    {"edge_depth_cap","edge_depth_cap"},{"edge_band_relief","edge_band_relief"},
    {"overmold_plug_width","overmold_plug_width"},{"overmold_copper_half_width","overmold_copper_half_width"},
    {"occ_step","occ_step"},{"frontier_half","frontier_half"},
    {"anchor_zone_weight","anchor_zone_weight"},{"anchor_som_weight","anchor_som_weight"},
    {"anchor_affinity_power","anchor_affinity_power"},{"reseat_evict_budget","reseat_evict_budget"},
    {"affinity_floor","affinity_floor"},{"refine_span","refine_span"}};
const std::vector<Binding> quantization_bindings{
    {"place_grid","kGridMm"},{"half_grid","kHalfMm"},{"quant_credit","kCreditMm"},
    {"snap_erosion","kSnapErosionMm"},{"outline_snap","kOutlineSnapMm"},
    {"fine_snap","kFineSnapMm"},{"via_impedance_cost","kViaImpedanceMm"}};
const std::vector<Binding> placement_bindings{
    {"zone_pack_fill","zone_pack_fill"},{"edge_zone_aspect","edge_zone_aspect"},
    {"interior_zone_aspect","interior_zone_aspect"},{"interior_band_target","interior_band_target"},
    {"d13_df40_min_pins","df40_min_pins"}};
}
NativeBoardPolicy make_native_board_policy(const ProjectPaths& paths,const FloorplanInput& in){
    if(paths.repository_root.empty())throw ProjectError("native board policy requires repository_root");
    if(!std::isfinite(in.cross_budget_k)||in.cross_budget_k<=0||!std::isfinite(in.place_clear)||in.place_clear<0)
        throw ProjectError("native board policy: invalid invocation parameters");
    if(in.experiment)validate_floorplan_experiment(*in.experiment);
    NativeBoardPolicy out;out.pipeline_metadata=native_board_pipeline_metadata();out.audit_sources=native_board_policy_audit_sources();
    const auto root=std::filesystem::absolute(paths.repository_root);
    out.compiler_include_flags={"-I"+(root/"native/include").string(),"-I"+(root/"native/src").string()};
    std::map<std::string,std::pair<std::string,std::function<JsonNode()>>> providers;
    const auto add=[&](const std::vector<Binding>& bindings,const std::string& prefix){
        for(const auto& b:bindings){const std::string name=b.name;
            providers.emplace(name,std::make_pair(prefix+b.symbol,[name]{
                FloorplanInput unused;const auto value=floorplan_live_assumption(name,unused);
                if(!value)throw ProjectError("native board provider disappeared: "+name);
                return number(*value);
            }));
        }
    };
    add(floor_bindings,"native/src/floorplan_internal.hpp::schgen::floorplan_detail::");
    add(quantization_bindings,"native/include/schgen/quantize.hpp::schgen::quantization_policy::");
    add(placement_bindings,"native/include/schgen/board_decision_policy.hpp::schgen::board_decision_policy::");
    // Own only invocation scalar parameters, not caller objects or observer
    // callbacks. An ordinary-cost override of zero is present, not a default.
    providers.emplace("cross_k",std::make_pair("native/include/schgen/floorplan.hpp::schgen::FloorplanInput::cross_budget_k",[value=in.cross_budget_k]{return number(value);}));
    providers.emplace("place_clear",std::make_pair("native/include/schgen/floorplan.hpp::schgen::FloorplanInput::place_clear",[value=in.place_clear]{return number(value);}));
    const auto ordinary_override=in.experiment?in.experiment->ordinary_via_mm:std::optional<double>{};
    providers.emplace("via_ordinary_cost",std::make_pair("native/include/schgen/quantize.hpp::schgen::quantization_policy::kViaOrdinaryMm",
        [ordinary_override]{return number(ordinary_override.value_or(quantization_policy::kViaOrdinaryMm));}));
    providers.emplace("zone_pad",std::make_pair("native/src/pcb_stage_internal.hpp::schgen::pcb_stage::zone_pad",[]{return number(pcb_stage::zone_pad);}));
    providers.emplace("place_clear_baseline",std::make_pair("native/src/pcb_stage_internal.hpp::schgen::pcb_stage::clear",[]{return number(pcb_stage::clear);}));
    providers.emplace("seat_slide",std::make_pair("native/src/pcb_stage_internal.hpp::schgen::pcb_stage::slide",[]{return number(pcb_stage::slide);}));
    providers.emplace("dispersion_max",std::make_pair("native/include/schgen/ratsnest_gate.hpp::schgen::ratsnest_dispersion_max",[]{return number(ratsnest_dispersion_max);}));
    providers.emplace("dispersion_small_n",std::make_pair("native/include/schgen/ratsnest_gate.hpp::schgen::ratsnest_small_n",[]{return number(ratsnest_small_n);}));
    const std::map<std::string,std::string> calc_covers{
        {"overmold_side_gap","native/src/floorplan_internal.hpp::schgen::floorplan_detail::overmold_gap"},
        {"edge_band","native/src/floorplan_internal.hpp::schgen::floorplan_detail::edge_band"},
        {"occ_punch_mask","native/src/floorplan_internal.hpp::schgen::floorplan_detail::occ_punch"}};
    for(const auto& m:floorplan_ledger_policy()){
        NativeLedgerDeclaration d;d.name=m.name;d.kind=m.kind;d.step=m.step;d.unit=m.unit;d.basis=m.basis;
        d.source=m.source;d.inputs=m.inputs;d.expression=m.expression;d.repeated=m.repeated;
        if(m.kind=="ASSUME"){
            const auto it=providers.find(m.name);
            if(it==providers.end())throw ProjectError("native board policy: unreviewed new assumption "+m.name);
            d.covers={it->second.first};d.resolve=it->second.second;
        }else{const auto it=calc_covers.find(m.name);if(it!=calc_covers.end())d.covers={it->second};}
        out.ledger_declarations.push_back(std::move(d));
    }
    return out;
}
std::string NativeBoardPolicy::report()const{
    std::ostringstream out;out<<"NATIVE BOARD POLICY: "<<(providers_complete()?"PROVIDERS COMPLETE":"INCOMPLETE")<<" — "<<ledger_declarations.size()<<" declarations, "<<missing_providers.size()<<" missing providers; source audit still required";
    for(const auto& g:missing_providers)out<<"\n  MISSING "<<g.name<<": "<<g.decision_source<<" — "<<g.action;
    return out.str();
}
NativeBoardPolicy configure_native_board_policy(BoardPipelineOptions& options,const ProjectPaths& paths,const FloorplanInput& in){
    if(!options.ledger_declarations.empty()||!options.audit_sources.empty()||!options.pipeline_metadata.stages.empty()||
       !options.pipeline_metadata.quantization.empty()||!options.pipeline_metadata.fallbacks.empty()||!options.pipeline_metadata.baselines.empty())
        throw ProjectError("native board policy: refusing to replace caller-supplied policy fields");
    auto policy=make_native_board_policy(paths,in);auto next=options;
    next.ledger_declarations=policy.ledger_declarations;next.pipeline_metadata=policy.pipeline_metadata;next.audit_sources=policy.audit_sources;
    for(const auto& flag:policy.compiler_include_flags)if(std::find(next.audit.flags.begin(),next.audit.flags.end(),flag)==next.audit.flags.end())next.audit.flags.push_back(flag);
    options=std::move(next);return policy;
}
}
