#include "floorplan_internal.hpp"

#include <algorithm>
#include <iomanip>
#include <sstream>

namespace schgen::floorplan_detail {
namespace {
struct Declaration {
    std::string name, kind, step, unit, basis, source, cover, expression;
    std::vector<std::string> inputs;
    double value;
};
// Declarative provenance ported from core/ledger.py, not a board-specific
// placement table. Input overrides are resolved below before recording.
const std::vector<Declaration> declarations{
    {"edge_margin","ASSUME","floorplan.sizing","mm","edge-run keep-in from each board corner","policy","floorplan.EDGE_MARGIN","", {}, 10.000000000000000},
    {"mh_corner_keepout","ASSUME","floorplan.sizing","mm","M3 corner mounting-hole exclusion square","policy","floorplan.MH_CORNER_KO","", {}, 10.000000000000000},
    {"edge_depth_cap","ASSUME","floorplan.sizing","mm","deepest inboard reach allowed to an edge block","policy","floorplan.EDGE_DEPTH_CAP","", {}, 15.000000000000000},
    {"edge_band_relief","ASSUME","floorplan.sizing","mm","seed-outline relief subtracted from edge_depth_cap","policy","floorplan.EDGE_BAND_RELIEF","", {}, 4.0000000000000000},
    {"edge_inset","ASSUME","floorplan.sizing","mm","connector face inset from the board outline","policy","floorplan.EDGE_INSET","", {}, 1.5000000000000000},
    {"cable_neighbor_gap","ASSUME","floorplan.sizing","mm","clear span between two overmolded cable plugs, charged ONCE per pair","physical","floorplan.CABLE_NEIGHBOR_GAP","", {}, 20.000000000000000},
    {"overmold_plug_width","ASSUME","floorplan.sizing","mm","widest HDMI overmold shell a mated cable presents","physical","floorplan.OVERMOLD_PLUG_W_MAX","", {}, 22.000000000000000},
    {"overmold_copper_half_width","ASSUME","floorplan.sizing","mm","half the receptacle copper footprint the shell overhangs","physical","floorplan.OVERMOLD_COPPER_HALF_W","", {}, 8.0000000000000000},
    {"block_clearance","ASSUME","floorplan.sizing","mm","minimum gap between two packed subsystem zones","policy","floorplan.CLEAR","", {}, 0.29999999999999999},
    {"perimeter_keepout","ASSUME","floorplan.sizing","mm","seed-outline perimeter band added on every side","policy","floorplan.PERIM_KEEPOUT","", {}, 3.0000000000000000},
    {"som_halo","ASSUME","floorplan.sizing","mm","keepout ring around the SoM body in the floorplan frame","policy","floorplan.SOM_HALO","", {}, 7.0000000000000000},
    {"pack_efficiency","ASSUME","floorplan.sizing","ratio","seed-outline area fill; the real pack re-proves it","fitted","floorplan.PACK_EFFICIENCY","", {}, 0.59999999999999998},
    {"occ_top_mask","ASSUME","floorplan.sizing","bitmask","occupancy bit for the top copper face","policy","floorplan.OCC_TOP","", {}, 1.0000000000000000},
    {"occ_bottom_mask","ASSUME","floorplan.sizing","bitmask","occupancy bit for the bottom copper face","policy","floorplan.OCC_BOTTOM","", {}, 2.0000000000000000},
    {"occ_step","ASSUME","floorplan.sizing","mm","candidate-pose lattice step of the occupancy search","policy","floorplan.OCC_STEP_MM","", {}, 1.0000000000000000},
    {"frontier_half","ASSUME","floorplan.sizing","mm","half-width of the place_near frontier bucket","policy","floorplan.FRONTIER_HALF_MM","", {}, 0.050000001000000002},
    {"som_seat_band","ASSUME","floorplan.sizing","mm","band reserved around each DF40 receptacle","policy","floorplan.SOM_SEAT_BAND_MM","", {}, 6.0000000000000000},
    {"som_occ_pad","ASSUME","floorplan.sizing","mm","pad grown around the SoM body rectangle when occupied","policy","floorplan.SOM_OCC_PAD_MM","", {}, 1.5000000000000000},
    {"anchor_zone_weight","ASSUME","floorplan.sizing","weight","zone-centroid term of the interior seat anchor","policy","floorplan.ANCHOR_ZONE_W","", {}, 0.25000000000000000},
    {"anchor_som_weight","ASSUME","floorplan.sizing","weight","SoM-pull term of the interior seat anchor","policy","floorplan.ANCHOR_SOM_W","", {}, 7.0000000000000000},
    {"anchor_affinity_power","ASSUME","floorplan.sizing","exponent","exponent applied to net affinity in the seat anchor","policy","floorplan.ANCHOR_AFF_POW","", {}, 1.6000000000000001},
    {"reseat_evict_budget","ASSUME","floorplan.sizing","evictions","successful eviction episodes one pack attempt may spend","policy","floorplan._RESEAT_EVICT_BUDGET","", {}, 3.0000000000000000},
    {"affinity_floor","ASSUME","floorplan.sizing","affinity","floor on every edge block's weight; it orders the zero-affinity ones","policy","floorplan.AFFINITY_FLOOR","", {}, 0.050000000000000003},
    {"placeholder_aspect","ASSUME","floorplan.sizing","w/h","target width/height of a reservation-only block's landing rectangle","policy","floorplan.PLACEHOLDER_ASPECT","", {}, 1.6000000000000001},
    {"placeholder_min","ASSUME","floorplan.sizing","mm","shortest side a placeholder landing rectangle may take","policy","floorplan.PLACEHOLDER_MIN_MM","", {}, 8.0000000000000000},
    {"placeholder_max","ASSUME","floorplan.sizing","mm","tallest a placeholder rectangle grows before it is widened instead","policy","floorplan.PLACEHOLDER_MAX_MM","", {}, 30.000000000000000},
    {"cross_k","ASSUME","floorplan.sizing","mm/mm/subsystem","LAW-5 airwire coefficient, fitted from two boards; NOT a physical law","fitted","config.CROSS_K","", {}, 3.0000000000000000},
    {"dispersion_max","ASSUME","floorplan.sizing","x","worst cluster bbox/ideal ratio the LAW-5 gate accepts","policy","ratsnest.DISPERSION_MAX","", {}, 9.0000000000000000},
    {"dispersion_small_n","ASSUME","floorplan.sizing","parts","cluster size below which dispersion is not judged","policy","ratsnest.SMALL_N","", {}, 3.0000000000000000},
    {"place_grid","ASSUME","floorplan.sizing","mm","KiCad placement grid the emitted SoM-J and MH poses snap to","standard","quantize.GRID_MM","", {}, 1.2700000000000000},
    {"half_grid","ASSUME","floorplan.sizing","mm","coarse 0.5 mm quantum of the legalizer and the SoM pose","policy","quantize.HALF_MM","", {}, 0.50000000000000000},
    {"quant_credit","ASSUME","floorplan.sizing","mm","credit that keeps a proven reach from rounding away","policy","quantize.CREDIT_MM","", {}, 0.050000000000000003},
    {"snap_erosion","ASSUME","floorplan.sizing","mm","declared margin on template bounds >= 5 mm","policy","quantize.SNAP_EROSION_MM","", {}, 0.75000000000000000},
    {"seat_slide","ASSUME","floorplan.sizing","mm","edge-seat courtyard-to-pad-flush slide allowance","policy","quantize.SEAT_SLIDE_MM","", {}, 1.2000000000000000},
    {"outline_snap","ASSUME","floorplan.sizing","mm","coarse outline grid every candidate board rounds up to","policy","quantize.OUTLINE_SNAP_MM","", {}, 5.0000000000000000},
    {"refine_span","ASSUME","floorplan.sizing","mm","window below the aspect-best that the fine scan sweeps","policy","quantize.REFINE_SPAN_MM","", {}, 40.000000000000000},
    {"fine_snap","ASSUME","floorplan.sizing","mm","fine outline grid; packing feasibility is jagged at 1 mm","policy","quantize.FINE_SNAP_MM","", {}, 1.0000000000000000},
    {"via_size","ASSUME","floorplan.sizing","mm","via barrel diameter charged by the sizing estimator","physical","quantize.VIA_SIZE_MM","", {}, 0.59999999999999998},
    {"via_clearance","ASSUME","floorplan.sizing","mm","annulus each via barrel takes out of a routing channel","physical","quantize.VIA_CLEAR_MM","", {}, 0.25000000000000000},
    {"stack_thickness","ASSUME","floorplan.sizing","mm","JLC04161H-7628 4-layer finished thickness","datasheet","quantize.STACK_THICKNESS_MM","", {}, 1.6000000000000001},
    {"zone_pad","ASSUME","floorplan.sizing","mm","pad kept between a zone box and the parts packed inside it","policy","pcbconst.ZONE_PAD","", {}, 0.29999999999999999},
    {"place_clear_baseline","ASSUME","floorplan.sizing","mm","shipped part-to-part clearance floor inside a zone","policy","pcbconst.PLACE_CLEAR_BASELINE","", {}, 0.50000000000000000},
    {"place_clear","ASSUME","floorplan.sizing","mm","part-to-part clearance in force (SCHGEN_PLACE_CLEAR)","policy","pcbconst.PLACE_CLEAR","", {}, 0.50000000000000000},
    {"zone_pack_fill","ASSUME","floorplan.sizing","ratio","shelf-pack target fill that sets each zone aspect","fitted","pcbconst.ZONE_PACK_FILL","", {}, 0.62000000000000000},
    {"zone_step","ASSUME","floorplan.sizing","mm","0.1 inch zone lattice pitch","standard","pcbconst.ZONE_STEP","", {}, 2.5400000000000000},
    {"edge_zone_aspect","ASSUME","floorplan.sizing","w/h","target width/height of a connector-bearing zone","policy","pcbconst.EDGE_ZONE_ASPECT","", {}, 2.2000000000000002},
    {"interior_zone_aspect","ASSUME","floorplan.sizing","w/h","target width/height of an interior zone","policy","pcbconst.INTERIOR_ZONE_ASPECT","", {}, 2.0000000000000000},
    {"interior_band_target","ASSUME","floorplan.sizing","mm","band height an interior zone aims to fit","policy","pcbconst.INTERIOR_ZONE_BAND_TARGET","", {}, 32.000000000000000},
    {"som_side_band","ASSUME","floorplan.sizing","mm","usable band beside the SoM body","policy","pcbconst.SOM_SIDE_BAND_MM","", {}, 39.500000000000000},
    {"som_decoupling_inset","ASSUME","floorplan.sizing","mm","inset of the bottom-side decoupling grid inside the SoM shadow","policy","placement.SOM_DECOUPLING_INSET","", {}, 6.0000000000000000},
    {"d13_min_subject_pins","ASSUME","floorplan.sizing","pins","pin count below which a part gets no D13 reach","policy","fanout.MIN_SUBJECT_PINS","", {}, 3.0000000000000000},
    {"d13_df40_min_pins","ASSUME","floorplan.sizing","pins","pin count that identifies a DF40 receptacle","physical","fanout.DF40_MIN_PINS","", {}, 40.000000000000000},
    {"overmold_side_gap","CALC","floorplan.sizing","mm","shell overhang beside a single receptacle","","floorplan.OVERMOLD_SIDE_GAP","plug_width / 2 - copper_half_width", {"plug_width","copper_half_width"}, 0.0},
    {"edge_band","CALC","floorplan.sizing","mm","connector band width used by the seed outline","","floorplan.EDGE_BAND","edge_depth_cap - edge_band_relief", {"edge_depth_cap","edge_band_relief"}, 0.0},
    {"occ_punch_mask","CALC","floorplan.sizing","bitmask","occupancy bits of geometry that pierces both faces","","floorplan.OCC_PUNCH","occ_top | occ_bottom", {"occ_top","occ_bottom"}, 0.0},
    {"est_via_ordinary","CALC","floorplan.sizing","mm","channel an ordinary layer change costs the sizing estimator","","quantize.EST_VIA_ORDINARY_MM","2 * (via_size + 2 * via_clearance)", {"via_size","via_clearance"}, 0.0},
    {"est_via_impedance","CALC","floorplan.sizing","mm","channel a controlled-impedance pair change costs the estimator","","","2 * 2 * (via_size + 2 * via_clearance) + 2 * stack_thickness", {"via_size","via_clearance","stack_thickness"}, 0.0},
    {"est_via_class_split","CALC","floorplan.sizing","nets","which nets are charged the impedance via row, and which are not","","","n_impedance = count(net whose class carries a DiffGeometry)", {"n_cross_nets","n_impedance","n_ordinary","impedance_classes"}, 0.0},
    {"subsystem_count","CALC","floorplan.sizing","subsystems","LAW-5 budget multiplier; a sheet miscount rescales the whole budget","","","n_sheets - n_som_j - n_mechanical_only", {"n_sheets","n_som_j","n_mechanical_only"}, 0.0},
    {"seed_outline","CALC","floorplan.sizing","mm","starting outline the aspect search grows from","","","max(som+2*halo+2*band, sqrt(area/fill + keepout_area) * aspect) + 2 * perimeter_keepout, snapped up to outline_snap", {"som_w","som_h","som_halo","edge_band","component_area","pack_efficiency","perimeter_keepout","seed_w","seed_h"}, 0.0},
    {"d13_tier_population","CALC","floorplan.sizing","parts","how many parts each D13 fan-out tier actually governed","","","intelligent_need(pins): pins<=2 -> 0.20, pins<=8 -> 1.50, else 2.00", {"n_subjects","tier_le2_0p20","tier_le8_1p50","tier_ge9_2p00"}, 0.0},
    {"decoupling_grid","CALC","floorplan.sizing","caps","the decoupling grid the sizing estimator prices under the SoM","","","grid = som - 2*inset; cols = max(1, min(n, round(sqrt(n*gw/gh)))); rows = ceil(n / cols)", {"n_caps","som_w","som_h","inset","grid_w","grid_h","cols","rows"}, 0.0},
    {"outline_candidates","CALC","sizing.pass","candidates","every candidate outline this pass judged, and why each was dropped","","","generated = reject_aspect + reject_min_area + reject_not_smaller + reject_pack + reject_law5_budget + accepted", {"generated","reject_aspect","reject_min_area","reject_not_smaller","reject_pack","reject_law5_budget","accepted"}, 0.0},
    {"law5_airwire_budget","CALC","sizing.pass","mm","LAW-5 budget at the winning outline of this pass","","","cross_k * (board_w * board_h) ** 0.5 * n_subsystems", {"cross_k","board_w","board_h","n_subsystems"}, 0.0},
    {"pass_winner","CALC","sizing.pass","mm","smallest-area outline this pass could prove","","","headroom = budget - est_cross", {"board_w","board_h","area","est_cross","budget","headroom"}, 0.0},
    {"side_choice","CALC","floorplan.sizing","side","per-block copper-face decision, judged by the airwire estimator","","","challenger wins iff est_challenger < est_incumbent - 1e-6", {"offered","est_incumbent","est_challenger","margin"}, 0.0},
    {"side_fixed","CALC","floorplan.sizing","side","per-block face that had no alternative to weigh","","","one face survived place_near, so no estimator judgement was made", {"offered","shape_idx"}, 0.0},
    {"side_census","CALC","floorplan.sizing","blocks","how many blocks were offered a second copper face, and what won","","","n_blocks = n_two_face + n_single_face", {"n_blocks","n_two_face","n_chose_bottom","n_single_face"}, 0.0},
    {"plan_choice","CALC","floorplan.sizing","plan","which bottom-surface reservation model sized the shipped board","","","keep free iff free_area < conservative_area or (equal area and free_est < conservative_est)", {"conservative_area","conservative_est","free_area","free_est"}, 0.0},
    {"sizing_winner","CALC","floorplan.sizing","mm","the outline the shipped board is built on","","floorplan.BOARD_W","headroom = budget - est_cross", {"board_w","board_h","area","est_cross","budget","headroom","plan"}, 0.0},
};
std::string pad(const std::string& value,std::size_t width) {
    return value+std::string(value.size()<width ? width-value.size():0,' ');
}
std::string shown(const JsonNode& value) {
    if (value.kind==JsonKind::String) return value.string_value;
    if (value.kind==JsonKind::Bool) return value.bool_value ? "yes":"no";
    if (value.kind!=JsonKind::Number) throw std::logic_error("floorplan ledger: non-scalar value");
    auto text=number(py_round(value.number_value,4),4);
    while (!text.empty() && text.back()=='0') text.pop_back();
    if (!text.empty() && text.back()=='.') text.pop_back();
    return text.empty() || text=="-0" ? "0":text;
}
}  // namespace

void Engine::ledger_open() {
    plan.accounting.decisions.push_back({"floorplan.sizing","STEP","floorplan.sizing",jvalue(""),{},0,"STEP   floorplan.sizing"});
    for (const auto& d:declarations) {
        if (d.kind!="ASSUME") continue;
        double value=d.value;
        if (d.name=="cross_k") value=in.cross_budget_k;
        if (d.name=="place_clear") value=in.place_clear;
        const auto v=jvalue(value);
        const auto text="  ASSUME "+pad(d.name,30)+" = "+pad(shown(v),13)+" "+pad(d.unit,10)+
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
        if (key=="label") { label=shown(v); continue; }
        keys.push_back(key);
        if (!ins.empty()) ins+=" ";
        ins+=key+"="+shown(v);
    }
    if (keys!=d.inputs) throw std::logic_error("floorplan ledger: calculation inputs drifted for "+repr(name));
    const int depth=step=="sizing.pass" ? 2:1;
    const auto display=name+(label.empty() ? "":"["+label+"]");
    const auto text=std::string(depth*2,' ')+"CALC   "+pad(display,30)+" = "+pad(shown(value),13)+" "+
        pad(d.unit,10)+" <- "+ins+"  ::  "+d.expression;
    plan.accounting.decisions.push_back({step,"CALC",name,std::move(value),std::move(inputs),depth,text});
}
}  // namespace schgen::floorplan_detail

namespace schgen {
std::string render_floorplan_ledger(const FloorplanPlan& plan) {
    std::string out;
    for (const auto& d:plan.accounting.decisions) out+=d.text+"\n";
    return out;
}
}  // namespace schgen
