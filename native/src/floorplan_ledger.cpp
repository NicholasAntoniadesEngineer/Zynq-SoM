#include "floorplan_internal.hpp"
#include "schgen/precision_ops.hpp"
#include "schgen/floorplan_ledger_policy.hpp"
#include "pcb_stage_internal.hpp"
#include "schgen/ratsnest_gate.hpp"
#include "schgen/board_decision_policy.hpp"

#include <algorithm>
#include <iomanip>
#include <sstream>

namespace schgen::floorplan_detail {
namespace {
struct Declaration {
    std::string name, kind, step, unit, basis, source, cover, expression;
    std::vector<std::string> inputs;
};
// Declarative provenance ported from core/ledger.py, not a board-specific
// placement table. Input overrides are resolved below before recording.
const std::vector<Declaration> declarations{
    {"edge_margin","ASSUME","floorplan.sizing","mm","edge-run keep-in from each board corner","policy","floorplan.EDGE_MARGIN","", {}},
    {"mh_corner_keepout","ASSUME","floorplan.sizing","mm","M3 corner mounting-hole exclusion square","policy","floorplan.MH_CORNER_KO","", {}},
    {"edge_depth_cap","ASSUME","floorplan.sizing","mm","deepest inboard reach allowed to an edge block","policy","floorplan.EDGE_DEPTH_CAP","", {}},
    {"edge_band_relief","ASSUME","floorplan.sizing","mm","seed-outline relief subtracted from edge_depth_cap","policy","floorplan.EDGE_BAND_RELIEF","", {}},
    {"edge_inset","ASSUME","floorplan.sizing","mm","connector face inset from the board outline","policy","floorplan.EDGE_INSET","", {}},
    {"cable_neighbor_gap","ASSUME","floorplan.sizing","mm","clear span between two overmolded cable plugs, charged ONCE per pair","physical","floorplan.CABLE_NEIGHBOR_GAP","", {}},
    {"overmold_plug_width","ASSUME","floorplan.sizing","mm","widest HDMI overmold shell a mated cable presents","physical","floorplan.OVERMOLD_PLUG_W_MAX","", {}},
    {"overmold_copper_half_width","ASSUME","floorplan.sizing","mm","half the receptacle copper footprint the shell overhangs","physical","floorplan.OVERMOLD_COPPER_HALF_W","", {}},
    {"block_clearance","ASSUME","floorplan.sizing","mm","minimum gap between two packed subsystem zones","policy","floorplan.CLEAR","", {}},
    {"perimeter_keepout","ASSUME","floorplan.sizing","mm","seed-outline perimeter band added on every side","policy","floorplan.PERIM_KEEPOUT","", {}},
    {"som_halo","ASSUME","floorplan.sizing","mm","keepout ring around the SoM body in the floorplan frame","policy","floorplan.SOM_HALO","", {}},
    {"pack_efficiency","ASSUME","floorplan.sizing","ratio","seed-outline area fill; the real pack re-proves it","fitted","floorplan.PACK_EFFICIENCY","", {}},
    {"occ_top_mask","ASSUME","floorplan.sizing","bitmask","occupancy bit for the top copper face","policy","floorplan.OCC_TOP","", {}},
    {"occ_bottom_mask","ASSUME","floorplan.sizing","bitmask","occupancy bit for the bottom copper face","policy","floorplan.OCC_BOTTOM","", {}},
    {"occ_step","ASSUME","floorplan.sizing","mm","candidate-pose lattice step of the occupancy search","policy","floorplan.OCC_STEP_MM","", {}},
    {"frontier_half","ASSUME","floorplan.sizing","mm","half-width of the place_near frontier bucket","policy","floorplan.FRONTIER_HALF_MM","", {}},
    {"som_seat_band","ASSUME","floorplan.sizing","mm","band reserved around each DF40 receptacle","policy","floorplan.SOM_SEAT_BAND_MM","", {}},
    {"som_occ_pad","ASSUME","floorplan.sizing","mm","pad grown around the SoM body rectangle when occupied","policy","floorplan.SOM_OCC_PAD_MM","", {}},
    {"anchor_zone_weight","ASSUME","floorplan.sizing","weight","zone-centroid term of the interior seat anchor","policy","floorplan.ANCHOR_ZONE_W","", {}},
    {"anchor_som_weight","ASSUME","floorplan.sizing","weight","SoM-pull term of the interior seat anchor","policy","floorplan.ANCHOR_SOM_W","", {}},
    {"anchor_affinity_power","ASSUME","floorplan.sizing","exponent","exponent applied to net affinity in the seat anchor","policy","floorplan.ANCHOR_AFF_POW","", {}},
    {"reseat_evict_budget","ASSUME","floorplan.sizing","evictions","successful eviction episodes one pack attempt may spend","policy","floorplan._RESEAT_EVICT_BUDGET","", {}},
    {"affinity_floor","ASSUME","floorplan.sizing","affinity","floor on every edge block's weight; it orders the zero-affinity ones","policy","floorplan.AFFINITY_FLOOR","", {}},
    {"cross_k","ASSUME","floorplan.sizing","mm/mm/subsystem","LAW-5 airwire coefficient, fitted from two boards; NOT a physical law","fitted","config.CROSS_K","", {}},
    {"dispersion_max","ASSUME","floorplan.sizing","x","worst cluster bbox/ideal ratio the LAW-5 gate accepts","policy","ratsnest.DISPERSION_MAX","", {}},
    {"dispersion_small_n","ASSUME","floorplan.sizing","parts","cluster size below which dispersion is not judged","policy","ratsnest.SMALL_N","", {}},
    {"place_grid","ASSUME","floorplan.sizing","mm","KiCad placement grid the emitted SoM-J and MH poses snap to","standard","quantize.GRID_MM","", {}},
    {"half_grid","ASSUME","floorplan.sizing","mm","coarse 0.5 mm quantum of the legalizer and the SoM pose","policy","quantize.HALF_MM","", {}},
    {"quant_credit","ASSUME","floorplan.sizing","mm","credit that keeps a proven reach from rounding away","policy","quantize.CREDIT_MM","", {}},
    {"snap_erosion","ASSUME","floorplan.sizing","mm","declared margin on template bounds >= 5 mm","policy","quantize.SNAP_EROSION_MM","", {}},
    {"seat_slide","ASSUME","floorplan.sizing","mm","edge-seat courtyard-to-pad-flush slide allowance","policy","quantize.SEAT_SLIDE_MM","", {}},
    {"outline_snap","ASSUME","floorplan.sizing","mm","coarse outline grid every candidate board rounds up to","policy","quantize.OUTLINE_SNAP_MM","", {}},
    {"refine_span","ASSUME","floorplan.sizing","mm","window below the aspect-best that the fine scan sweeps","policy","quantize.REFINE_SPAN_MM","", {}},
    {"fine_snap","ASSUME","floorplan.sizing","mm","fine outline grid; packing feasibility is jagged at 1 mm","policy","quantize.FINE_SNAP_MM","", {}},
    {"via_ordinary_cost","ASSUME","floorplan.sizing","mm","compiled ordinary-net estimator cost; actual ordinary_via_mm override takes precedence","policy","quantization_policy.kViaOrdinaryMm","", {}},
    {"via_impedance_cost","ASSUME","floorplan.sizing","mm","compiled impedance-net estimator cost; no physical operand reconstruction","policy","quantization_policy.kViaImpedanceMm","", {}},
    {"zone_pad","ASSUME","floorplan.sizing","mm","pad kept between a zone box and the parts packed inside it","policy","pcbconst.ZONE_PAD","", {}},
    {"place_clear_baseline","ASSUME","floorplan.sizing","mm","shipped part-to-part clearance floor inside a zone","policy","pcbconst.PLACE_CLEAR_BASELINE","", {}},
    {"place_clear","ASSUME","floorplan.sizing","mm","part-to-part clearance in force (SCHGEN_PLACE_CLEAR)","policy","pcbconst.PLACE_CLEAR","", {}},
    {"zone_pack_fill","ASSUME","floorplan.sizing","ratio","shelf-pack target fill that sets each zone aspect","fitted","pcbconst.ZONE_PACK_FILL","", {}},
    {"edge_zone_aspect","ASSUME","floorplan.sizing","w/h","target width/height of a connector-bearing zone","policy","pcbconst.EDGE_ZONE_ASPECT","", {}},
    {"interior_zone_aspect","ASSUME","floorplan.sizing","w/h","target width/height of an interior zone","policy","pcbconst.INTERIOR_ZONE_ASPECT","", {}},
    {"interior_band_target","ASSUME","floorplan.sizing","mm","band height an interior zone aims to fit","policy","pcbconst.INTERIOR_ZONE_BAND_TARGET","", {}},
    {"som_decoupling_inset","ASSUME","floorplan.sizing","mm","inset of the bottom-side decoupling grid inside the SoM shadow","policy","placement.SOM_DECOUPLING_INSET","", {}},
    {"d13_min_subject_pins","ASSUME","floorplan.sizing","pins","pin count below which a part gets no D13 reach","policy","fanout.MIN_SUBJECT_PINS","", {}},
    {"d13_df40_min_pins","ASSUME","floorplan.sizing","pins","pin count that identifies a DF40 receptacle","physical","fanout.DF40_MIN_PINS","", {}},
    {"breathe_epsilon","ASSUME","floorplan.sizing","mm","comparison tolerance in existing breathe clearance, progress and dispersion checks","policy","board_decision_policy.breathe_epsilon_mm","", {}},
    {"breathe_search_step","ASSUME","floorplan.sizing","mm","increment and retreat step in existing breathe displacement search","policy","board_decision_policy.breathe_step_mm","", {}},
    {"mounting_hole_inset","ASSUME","floorplan.sizing","mm","mounting-hole center inset used by the cross-net geometry estimator","policy","floorplan.mh_inset","", {}},
    {"edge_pad_clearance","ASSUME","floorplan.sizing","mm","connector pad clearance from the outline used by the cross-net geometry estimator","policy","floorplan.edge_pad_clear","", {}},
    {"compose_guard","ASSUME","floorplan.sizing","mm","margin subtracted from near bounds during composition","policy","board_decision_policy.compose.guard_mm","", {}},
    {"compose_repair_max","ASSUME","floorplan.sizing","iterations","maximum iterations of composition constraint repair","policy","board_decision_policy.compose.repair_max","", {}},
    {"compose_median_passes","ASSUME","floorplan.sizing","passes","weighted median passes for composition refinement","policy","board_decision_policy.compose.median_passes","", {}},
    {"compose_channel_min_nets","ASSUME","floorplan.sizing","nets","minimum channel demand that receives a separation constraint","policy","board_decision_policy.compose.channel_min_nets","", {}},
    {"compose_channel_floor","ASSUME","floorplan.sizing","mm","minimum reserved channel separation","policy","board_decision_policy.compose.channel_floor","", {}},
    {"compose_channel_per_net","ASSUME","floorplan.sizing","mm/net","additional channel separation per demanded net","policy","board_decision_policy.compose.channel_per_net","", {}},
    {"compose_hop_weight","ASSUME","floorplan.sizing","weight","flow-hop attraction weight in composition refinement","policy","board_decision_policy.compose.hop_weight","", {}},
    {"compose_seed_weight","ASSUME","floorplan.sizing","weight","seed-position retention weight in composition refinement","policy","board_decision_policy.compose.seed_weight","", {}},
    {"floorplan_svg_origin_x","ASSUME","floorplan.sizing","px","horizontal drawing origin of the floorplan SVG","policy","board_decision_policy.svg.ox","", {}},
    {"floorplan_svg_origin_y","ASSUME","floorplan.sizing","px","vertical drawing origin of the floorplan SVG","policy","board_decision_policy.svg.oy","", {}},
    {"floorplan_svg_scale","ASSUME","floorplan.sizing","px/mm","floorplan SVG drawing scale","policy","board_decision_policy.svg.scale","", {}},
    {"escape_construct_radius","ASSUME","floorplan.sizing","mm","escape corridor construction reach","policy","board_decision_policy.escape.radius","", {}},
    {"escape_lattice","ASSUME","floorplan.sizing","mm","escape via search lattice spacing","policy","board_decision_policy.escape.lattice","", {}},
    {"escape_lane_handle","ASSUME","floorplan.sizing","mm","escape lane extent beyond the connector contact row","policy","board_decision_policy.escape.lane_handle","", {}},
    {"escape_hole_clearance","ASSUME","floorplan.sizing","mm","minimum hole-to-hole separation in escape search","policy","board_decision_policy.escape.hole_hole","", {}},
    {"small_part_routing_factor","ASSUME","floorplan.sizing","ratio","area multiplier for small-part routing reserve; also reported by the plan","policy","board_decision_policy.floorplan.small_part_routing_factor","", {}},
    {"point_segment_tolerance","ASSUME","floorplan.sizing","mm","axis recognition and endpoint tolerance in point-on-segment tests","policy","board_decision_policy.pack.point_segment_tolerance_mm","", {}},
    {"visual_axis_tolerance","ASSUME","floorplan.sizing","mm","axis recognition and strict interior tolerance in visual crossing tests","policy","board_decision_policy.pack.visual_axis_tolerance_mm","", {}},
    {"collinear_overlap_tolerance","ASSUME","floorplan.sizing","mm","axis recognition and minimum strict collinear overlap","policy","board_decision_policy.pack.collinear_overlap_tolerance_mm","", {}},
    {"segment_cross_tolerance","ASSUME","floorplan.sizing","mm^2","signed cross-product threshold for strict segment intersection","policy","board_decision_policy.pack.segment_cross_tolerance_mm2","", {}},
    {"label_courtyard_gap","ASSUME","floorplan.sizing","mm","clear-label search offset outside the footprint courtyard","policy","board_decision_policy.pack.label_courtyard_gap_mm","", {}},
    {"label_orbit_tau","ASSUME","floorplan.sizing","radian","established full-turn double used by the sixteen-angle label orbit","policy","board_decision_policy.pack.label_orbit_tau","", {}},
    {"overmold_side_gap","CALC","floorplan.sizing","mm","shell overhang beside a single receptacle","","floorplan.OVERMOLD_SIDE_GAP","plug_width / 2 - copper_half_width", {"plug_width","copper_half_width"}},
    {"edge_band","CALC","floorplan.sizing","mm","connector band width used by the seed outline","","floorplan.EDGE_BAND","edge_depth_cap - edge_band_relief", {"edge_depth_cap","edge_band_relief"}},
    {"occ_punch_mask","CALC","floorplan.sizing","bitmask","occupancy bits of geometry that pierces both faces","","floorplan.OCC_PUNCH","occ_top | occ_bottom", {"occ_top","occ_bottom"}},
    {"est_via_ordinary","CALC","floorplan.sizing","mm","channel an ordinary layer change costs the sizing estimator","","","resolved ordinary estimator cost (caller override when supplied)", {"via_cost"}},
    {"est_via_impedance","CALC","floorplan.sizing","mm","channel a controlled-impedance pair change costs the estimator","","","compiled impedance estimator cost", {"via_cost"}},
    {"est_via_class_split","CALC","floorplan.sizing","nets","which nets are charged the impedance via row, and which are not","","","n_impedance = count(net whose class carries a DiffGeometry)", {"n_cross_nets","n_impedance","n_ordinary","impedance_classes"}},
    {"subsystem_count","CALC","floorplan.sizing","subsystems","LAW-5 budget multiplier; a sheet miscount rescales the whole budget","","","n_sheets - n_som_j - n_mechanical_only", {"n_sheets","n_som_j","n_mechanical_only"}},
    {"seed_outline","CALC","floorplan.sizing","mm","starting outline the aspect search grows from","","","max(som+2*halo+2*band, sqrt(area/fill + keepout_area) * aspect) + 2 * perimeter_keepout, snapped up to outline_snap", {"som_w","som_h","som_halo","edge_band","component_area","pack_efficiency","perimeter_keepout","seed_w","seed_h"}},
    {"d13_tier_population","CALC","floorplan.sizing","parts","how many parts each D13 fan-out tier actually governed","","","intelligent_need(pins): pins<=2 -> 0.20, pins<=8 -> 1.50, else 2.00", {"n_subjects","tier_le2_0p20","tier_le8_1p50","tier_ge9_2p00"}},
    {"decoupling_grid","CALC","floorplan.sizing","caps","the decoupling grid the sizing estimator prices under the SoM","","","grid = som - 2*inset; cols = max(1, min(n, round(sqrt(n*gw/gh)))); rows = ceil(n / cols)", {"n_caps","som_w","som_h","inset","grid_w","grid_h","cols","rows"}},
    {"outline_candidates","CALC","sizing.pass","candidates","every candidate outline this pass judged, and why each was dropped","","","generated = reject_aspect + reject_min_area + reject_not_smaller + reject_pack + reject_law5_budget + accepted", {"generated","reject_aspect","reject_min_area","reject_not_smaller","reject_pack","reject_law5_budget","accepted"}},
    {"law5_airwire_budget","CALC","sizing.pass","mm","LAW-5 budget at the winning outline of this pass","","","cross_k * (board_w * board_h) ** 0.5 * n_subsystems", {"cross_k","board_w","board_h","n_subsystems"}},
    {"pass_winner","CALC","sizing.pass","mm","smallest-area outline this pass could prove","","","headroom = budget - est_cross", {"board_w","board_h","area","est_cross","budget","headroom"}},
    {"side_choice","CALC","floorplan.sizing","side","per-block copper-face decision, judged by the airwire estimator","","","challenger wins iff est_challenger < est_incumbent - 1e-6", {"offered","est_incumbent","est_challenger","margin"}},
    {"side_fixed","CALC","floorplan.sizing","side","per-block face that had no alternative to weigh","","","one face survived place_near, so no estimator judgement was made", {"offered","shape_idx"}},
    {"side_census","CALC","floorplan.sizing","blocks","how many blocks were offered a second copper face, and what won","","","n_blocks = n_two_face + n_single_face", {"n_blocks","n_two_face","n_chose_bottom","n_single_face"}},
    {"plan_choice","CALC","floorplan.sizing","plan","which bottom-surface reservation model sized the shipped board","","","keep free iff free_area < conservative_area or (equal area and free_est < conservative_est)", {"conservative_area","conservative_est","free_area","free_est"}},
    {"sizing_winner","CALC","floorplan.sizing","mm","the outline the shipped board is built on","","floorplan.BOARD_W","headroom = budget - est_cross", {"board_w","board_h","area","est_cross","budget","headroom","plan"}},
};
std::string pad(const std::string& value,std::size_t width) {
    return value+std::string(value.size()<width ? width-value.size():0,' ');
}
std::string shown(const JsonNode& value,QuantizationCounts& counts) {
    if (value.kind==JsonKind::String) return value.string_value;
    if (value.kind==JsonKind::Bool) return value.bool_value ? "yes":"no";
    if (value.kind!=JsonKind::Number) throw std::logic_error("floorplan ledger: non-scalar value");
    // Numeric decision construction owns the actual work. Cached ledger
    // rendering below simply reads stored text and never revisits this call.
    static const std::string name="floorplan_ledger_display_precision4dp";
    checked_quantization_add(counts,name);
    auto text=number(floorplan_ledger_display_precision4dp(value.number_value),4);
    while (!text.empty() && text.back()=='0') text.pop_back();
    if (!text.empty() && text.back()=='.') text.pop_back();
    return text.empty() || text=="-0" ? "0":text;
}
}  // namespace

void Engine::ledger_open() {
    plan.accounting.decisions.push_back({"floorplan.sizing","STEP","floorplan.sizing",jvalue(""),{},0,"STEP   floorplan.sizing"});
    for (const auto& d:declarations) {
        if (d.kind!="ASSUME") continue;
        const auto value=schgen::floorplan_live_assumption(d.name,in);
        if(!value)throw std::logic_error("floorplan ledger: missing live assumption "+d.name);
        const auto v=jvalue(*value);
        const auto text="  ASSUME "+pad(d.name,30)+" = "+pad(shown(v,plan.accounting.quantization_engagements),13)+" "+pad(d.unit,10)+
            " ["+d.source+"] "+d.cover+" — "+d.basis;
        plan.accounting.decisions.push_back({d.step,d.kind,d.name,v,{},1,text});
    }
}
void Engine::ledger_pass(bool free) {
    const auto label=free ? "punch=free":"punch=conservative";
    plan.accounting.decisions.push_back({"floorplan.sizing","STEP","sizing.pass",jvalue(label),{},1,
                                        std::string("  STEP   sizing.pass  ")+label});
}
void Engine::calc(const std::string& name,JsonNode value,
                  std::vector<std::pair<std::string,JsonNode>> inputs,const std::string& step) {
    const auto found=std::find_if(declarations.begin(),declarations.end(),[&](const auto& d){return d.name==name;});
    if (found==declarations.end() || found->kind!="CALC")
        throw std::logic_error("floorplan ledger: unregistered calculation "+repr(name));
    const auto& d=*found;
    if (step!=d.step) throw std::logic_error("floorplan ledger: wrong step for "+repr(name));
    std::string label;
    std::vector<std::string> keys;
    std::string ins;
    for (const auto& [key,v]:inputs) {
        if (key=="label") { label=shown(v,plan.accounting.quantization_engagements); continue; }
        keys.push_back(key);
        if (!ins.empty()) ins+=" ";
        ins+=key+"="+shown(v,plan.accounting.quantization_engagements);
    }
    if (keys!=d.inputs) throw std::logic_error("floorplan ledger: calculation inputs drifted for "+repr(name));
    const int depth=step=="sizing.pass" ? 2:1;
    const auto display=name+(label.empty() ? "":"["+label+"]");
    const auto text=std::string(depth*2,' ')+"CALC   "+pad(display,30)+" = "+pad(shown(value,plan.accounting.quantization_engagements),13)+" "+
        pad(d.unit,10)+" <- "+ins+"  ::  "+d.expression;
    plan.accounting.decisions.push_back({step,"CALC",name,std::move(value),std::move(inputs),depth,text});
}
}  // namespace schgen::floorplan_detail

namespace schgen {
std::vector<FloorplanLedgerMigration> floorplan_ledger_migrations() {
    return {
        {"placeholder_aspect","retired","No native board caller of the parameterized interior_dims kernel",{}},
        {"placeholder_min","retired","No native board caller of the parameterized interior_dims kernel",{}},
        {"placeholder_max","retired","No native board caller of the parameterized interior_dims kernel",{}},
        {"zone_step","retired","Unused historical zone lattice; native packing has no consumer",{}},
        {"som_side_band","retired","Unused historical SoM-side band; native packing has no consumer",{}},
        {"via_size","replaced","Estimator uses compiled costs, not a barrel-diameter calculation",{"via_ordinary_cost","via_impedance_cost"}},
        {"via_clearance","replaced","Estimator uses compiled costs, not an annulus calculation",{"via_ordinary_cost","via_impedance_cost"}},
        {"stack_thickness","replaced","Estimator uses a compiled impedance cost, not the emitter stack thickness",{"via_impedance_cost"}},
        {"breathe_epsilon","exposed","Existing local 1e-4 comparison tolerance moved to shared live producer policy",{}},
        {"breathe_search_step","exposed","Existing local .25 search increment moved to shared live producer policy",{}}};
}
std::vector<FloorplanLedgerPolicy> floorplan_ledger_policy() {
    std::vector<FloorplanLedgerPolicy> out;
    const std::set<std::string> repeated{
        "outline_candidates","law5_airwire_budget","pass_winner","side_choice","side_fixed"};
    for (const auto& d:floorplan_detail::declarations)
        out.push_back({d.name,d.kind,d.step,d.unit,d.basis,d.source,d.cover,d.expression,
                       d.inputs,repeated.count(d.name)!=0});
    return out;
}
std::optional<double> floorplan_live_assumption(const std::string& name,const FloorplanInput& in) {
    using namespace floorplan_detail;
    if(name=="edge_margin")return edge_margin;
    if(name=="mounting_hole_inset")return mh_inset;
    if(name=="edge_pad_clearance")return edge_pad_clear;
    if(name=="compose_guard")return board_decision_policy::compose::guard_mm;
    if(name=="compose_repair_max")return board_decision_policy::compose::repair_max;
    if(name=="compose_median_passes")return board_decision_policy::compose::median_passes;
    if(name=="compose_channel_min_nets")return board_decision_policy::compose::channel_min_nets;
    if(name=="compose_channel_floor")return board_decision_policy::compose::channel_floor;
    if(name=="compose_channel_per_net")return board_decision_policy::compose::channel_per_net;
    if(name=="compose_hop_weight")return board_decision_policy::compose::hop_weight;
    if(name=="compose_seed_weight")return board_decision_policy::compose::seed_weight;
    if(name=="floorplan_svg_origin_x")return board_decision_policy::svg::ox;
    if(name=="floorplan_svg_origin_y")return board_decision_policy::svg::oy;
    if(name=="floorplan_svg_scale")return board_decision_policy::svg::scale;
    if(name=="escape_construct_radius")return board_decision_policy::escape::radius;
    if(name=="escape_lattice")return board_decision_policy::escape::lattice;
    if(name=="escape_lane_handle")return board_decision_policy::escape::lane_handle;
    if(name=="escape_hole_clearance")return board_decision_policy::escape::hole_hole;
    if(name=="mh_corner_keepout")return mh_corner;
    if(name=="edge_inset")return edge_inset;
    if(name=="cable_neighbor_gap")return cable_gap;
    if(name=="small_part_routing_factor")return board_decision_policy::floorplan::small_part_routing_factor;
    if(name=="point_segment_tolerance")return board_decision_policy::pack::point_segment_tolerance_mm;
    if(name=="visual_axis_tolerance")return board_decision_policy::pack::visual_axis_tolerance_mm;
    if(name=="collinear_overlap_tolerance")return board_decision_policy::pack::collinear_overlap_tolerance_mm;
    if(name=="segment_cross_tolerance")return board_decision_policy::pack::segment_cross_tolerance_mm2;
    if(name=="label_courtyard_gap")return board_decision_policy::pack::label_courtyard_gap_mm;
    if(name=="label_orbit_tau")return board_decision_policy::pack::label_orbit_tau;
    if(name=="block_clearance")return clear;
    if(name=="perimeter_keepout")return perimeter;
    if(name=="som_halo")return som_halo;
    if(name=="pack_efficiency")return fill;
    if(name=="occ_top_mask")return occ_top;
    if(name=="occ_bottom_mask")return occ_bottom;
    if(name=="som_seat_band")return som_seat_band;
    if(name=="som_occ_pad")return som_pad;
    if(name=="som_decoupling_inset")return dec_inset;
    if(name=="d13_min_subject_pins")return min_subject_pins;
    if(name=="edge_depth_cap")return edge_depth_cap;
    if(name=="edge_band_relief")return edge_band_relief;
    if(name=="overmold_plug_width")return overmold_plug_width;
    if(name=="overmold_copper_half_width")return overmold_copper_half_width;
    if(name=="occ_step")return occ_step;
    if(name=="frontier_half")return frontier_half;
    if(name=="anchor_zone_weight")return anchor_zone_weight;
    if(name=="anchor_som_weight")return anchor_som_weight;
    if(name=="anchor_affinity_power")return anchor_affinity_power;
    if(name=="reseat_evict_budget")return reseat_evict_budget;
    if(name=="affinity_floor")return affinity_floor;
    if(name=="refine_span")return refine_span;
    if(name=="place_grid")return quantization_policy::kGridMm;
    if(name=="half_grid")return quantization_policy::kHalfMm;
    if(name=="quant_credit")return quantization_policy::kCreditMm;
    if(name=="snap_erosion")return quantization_policy::kSnapErosionMm;
    if(name=="outline_snap")return quantization_policy::kOutlineSnapMm;
    if(name=="fine_snap")return quantization_policy::kFineSnapMm;
    if(name=="via_ordinary_cost")return floorplan_experiment_via_cost(in.experiment.get(),false,quantization_policy::kViaOrdinaryMm);
    if(name=="via_impedance_cost")return floorplan_experiment_via_cost(in.experiment.get(),true,quantization_policy::kViaImpedanceMm);
    if(name=="zone_pack_fill")return board_decision_policy::zone_pack_fill;
    if(name=="edge_zone_aspect")return board_decision_policy::edge_zone_aspect;
    if(name=="interior_zone_aspect")return board_decision_policy::interior_zone_aspect;
    if(name=="interior_band_target")return board_decision_policy::interior_band_target;
    if(name=="d13_df40_min_pins")return board_decision_policy::df40_min_pins;
    if(name=="breathe_epsilon")return board_decision_policy::breathe_epsilon_mm;
    if(name=="breathe_search_step")return board_decision_policy::breathe_step_mm;
    if(name=="zone_pad")return pcb_stage::zone_pad;
    if(name=="place_clear_baseline")return pcb_stage::clear;
    if(name=="seat_slide")return pcb_stage::slide;
    if(name=="dispersion_max")return ratsnest_dispersion_max;
    if(name=="dispersion_small_n")return ratsnest_small_n;
    if(name=="cross_k")return in.cross_budget_k;
    if(name=="place_clear")return in.place_clear;
    return std::nullopt;
}
std::string render_floorplan_ledger(const FloorplanPlan& plan) {
    std::string out;
    for (const auto& d:plan.accounting.decisions) out+=d.text+"\n";
    return out;
}
}  // namespace schgen
