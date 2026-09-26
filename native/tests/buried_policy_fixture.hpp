#pragma once
#include "schgen/floorplan_ledger_policy.hpp"
#include <array>
#include <cstring>
#include <stdexcept>

// Test-only additive provenance. These literal expectations are independent of
// production declarations and scanner output. Validate every new byte/value
// before comparing the remaining unchanged output to immutable old snapshots.
namespace buried_policy_fixture {
struct Addition {const char *name,*unit,*basis,*cover;double value;const char* text;};
inline const std::array<Addition,7> additions{{
    {"small_part_routing_factor","ratio","area multiplier for small-part routing reserve; also reported by the plan","board_decision_policy.floorplan.small_part_routing_factor",3.5,"  ASSUME small_part_routing_factor      = 3.5           ratio      [policy] board_decision_policy.floorplan.small_part_routing_factor — area multiplier for small-part routing reserve; also reported by the plan"},
    {"point_segment_tolerance","mm","axis recognition and endpoint tolerance in point-on-segment tests","board_decision_policy.pack.point_segment_tolerance_mm",0.000001,"  ASSUME point_segment_tolerance        = 0             mm         [policy] board_decision_policy.pack.point_segment_tolerance_mm — axis recognition and endpoint tolerance in point-on-segment tests"},
    {"visual_axis_tolerance","mm","axis recognition and strict interior tolerance in visual crossing tests","board_decision_policy.pack.visual_axis_tolerance_mm",0.000001,"  ASSUME visual_axis_tolerance          = 0             mm         [policy] board_decision_policy.pack.visual_axis_tolerance_mm — axis recognition and strict interior tolerance in visual crossing tests"},
    {"collinear_overlap_tolerance","mm","axis recognition and minimum strict collinear overlap","board_decision_policy.pack.collinear_overlap_tolerance_mm",0.000001,"  ASSUME collinear_overlap_tolerance    = 0             mm         [policy] board_decision_policy.pack.collinear_overlap_tolerance_mm — axis recognition and minimum strict collinear overlap"},
    {"segment_cross_tolerance","mm^2","signed cross-product threshold for strict segment intersection","board_decision_policy.pack.segment_cross_tolerance_mm2",1e-9,"  ASSUME segment_cross_tolerance        = 0             mm^2       [policy] board_decision_policy.pack.segment_cross_tolerance_mm2 — signed cross-product threshold for strict segment intersection"},
    {"label_courtyard_gap","mm","clear-label search offset outside the footprint courtyard","board_decision_policy.pack.label_courtyard_gap_mm",0.9,"  ASSUME label_courtyard_gap            = 0.9           mm         [policy] board_decision_policy.pack.label_courtyard_gap_mm — clear-label search offset outside the footprint courtyard"},
    {"label_orbit_tau","radian","established full-turn double used by the sixteen-angle label orbit","board_decision_policy.pack.label_orbit_tau",6.283185307179586,"  ASSUME label_orbit_tau                = 6.2832        radian     [policy] board_decision_policy.pack.label_orbit_tau — established full-turn double used by the sixteen-angle label orbit"}
}};
inline void demand(bool ok){if(!ok)throw std::runtime_error("buried policy additive provenance mismatch");}
inline bool bits(double a,double b){return std::memcmp(&a,&b,sizeof a)==0;}
inline std::vector<schgen::FloorplanLedgerPolicy> prior_policy(std::vector<schgen::FloorplanLedgerPolicy> rows){
    for(const auto& e:additions){
        auto found=rows.end();std::size_t count=0;
        for(auto i=rows.begin();i!=rows.end();++i)if(i->name==e.name){found=i;++count;}
        demand(count==1);const auto& r=*found;
        demand(r.kind=="ASSUME"&&r.step=="floorplan.sizing"&&r.unit==e.unit&&r.basis==e.basis&&
            r.source=="policy"&&r.legacy_cover==e.cover&&r.expression.empty()&&r.inputs.empty()&&!r.repeated);
        rows.erase(found);
    }
    demand(rows.size()==83);return rows;
}
inline schgen::FloorplanPlan prior_plan(schgen::FloorplanPlan plan){
    for(const auto& e:additions){
        auto& rows=plan.accounting.decisions;auto found=rows.end();std::size_t count=0;
        for(auto i=rows.begin();i!=rows.end();++i)if(i->name==e.name){found=i;++count;}
        demand(count==1);const auto& r=*found;
        demand(r.kind=="ASSUME"&&r.step=="floorplan.sizing"&&r.depth==1&&r.inputs.empty()&&
            r.value.kind==schgen::JsonKind::Number&&bits(r.value.number_value,e.value)&&r.text==e.text);
        rows.erase(found);
    }
    return plan;
}
// Only the seven independently entry-proved numeric ASSUME displays differ.
// Missing/too-small receipts are errors, not an optional compatibility path.
inline schgen::QuantizationCounts prior_display_counts(schgen::QuantizationCounts counts){
    const auto found=counts.find("floorplan_ledger_display_precision4dp");
    demand(found!=counts.end()&&found->second>7);
    found->second-=7;
    return counts;
}
inline schgen::FloorplanPlan prior_accounted_plan(schgen::FloorplanPlan plan){
    (void)prior_policy(schgen::floorplan_ledger_policy());
    plan=prior_plan(std::move(plan));
    plan.accounting.quantization_engagements=prior_display_counts(plan.accounting.quantization_engagements);
    return plan;
}
}
