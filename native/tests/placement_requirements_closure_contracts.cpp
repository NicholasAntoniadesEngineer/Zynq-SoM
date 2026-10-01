#include "schgen/board_pipeline.hpp"
#include <algorithm>
#include <iostream>

// Independent aggregation-policy test; not a fabricated production board run.
// Must be registered together with the parent-owned required-vector addition.
int main() {
    using namespace schgen;
    try {
        BoardPipelineResult result;result.sheets=1;
        for(const auto* name:{"inputs","authoring_purity","subsystem_structure","carrier_structure","sheet_gates","cc","symbol_law","link","board_schematic","constraints","diagram","bom_footprints","power_tree","rail_ampacity","testpoints","design_rules","part_rules","bom_values","footprint_pads","spice","pcb","pcb_drc","pcb_geometry","assembly","thermal","copper_debt","fab_profile","xdc","vivado","firmware","manual","testplan","gallery","devicetree","scfw","power_sequence","floorplan","quantize_census","fallbacks","stage_movement","pipeline_doc","model3d","si","manifest","ledger","placement_requirements"})
            result.gates.push_back({name,true,BoardGateStatus::passed,"aggregation fixture"});
        if(!result.ok()||!result.complete())throw std::runtime_error("baseline must contain all required gates");
        auto omitted=result;
        omitted.gates.erase(std::remove_if(omitted.gates.begin(),omitted.gates.end(),[](const auto& g){return g.name=="placement_requirements";}),omitted.gates.end());
        if(omitted.ok()||omitted.complete())throw std::runtime_error("missing placement_requirements escaped required-vector closure");
        for(const auto status:{BoardGateStatus::failed,BoardGateStatus::skipped,BoardGateStatus::unavailable}) {
            auto bad=result;bad.gates.back().status=status;bad.gates.back().mandatory=false;
            if(bad.ok())throw std::runtime_error("placement requirement status/mandatory downgrade escaped");
        }
        auto duplicate=result;duplicate.gates.push_back(result.gates.back());
        if(duplicate.ok())throw std::runtime_error("duplicate gate escaped");
        std::cout<<"PASS placement_requirements missing/status/mandatory/duplicate closure\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
