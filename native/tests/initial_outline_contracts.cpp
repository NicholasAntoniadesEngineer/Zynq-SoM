#include "floorplan_internal.hpp"
#include <iostream>
#include <cmath>
#include <limits>
using namespace schgen;
namespace {
void require(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
FloorplanInput fixture() {
    FloorplanInput in;in.som.w=in.som.h=20;in.compact_search=true;
    CircuitSheetIr sheet;sheet.name="edge";in.sheets.push_back(sheet);
    in.geometry.zone_box["edge"]={30,10};in.spec.emplace();in.spec->edges["N"]={"edge"};
    return in;
}
void objective_bound() {
    for(bool seeded:{false,true}) {
        auto in=fixture();in.geometry.zone_box["edge"]={60,10};
        auto observer=std::make_shared<FloorplanExperiment>();in.experiment=observer;
        if(seeded)observer->initial_outline={{80.0001,79.9999}};
        std::map<bool,double> best_area;
        std::map<bool,bool> equal_area_seen;
        observer->attempt_completed=[&](const auto& row) {
            // No nets or alternative shapes: every packed witness has cost
            // zero and meets the budget. Integer/near-integer test areas avoid
            // halfway ambiguity in this independent rounded-area calculation.
            const double area=std::nearbyint(row.w*row.h*10)/10;
            const auto best=best_area.find(row.punch_free);
            require(best==best_area.end() || area<=best->second,
                "attempted an area already dominated by a feasible incumbent");
            if(row.packed)best_area[row.punch_free]=area;
            if(row.packed && row.w==80 && row.h==80)equal_area_seen[row.punch_free]=true;
        };
        const auto result=build_floorplan(in);
        require(best_area.size()==2&&result.board_w>=80,"both independently feasible policies searched");
        if(seeded)require(equal_area_seen[false]&&equal_area_seen[true],
            "equal rounded area with preferable width was incorrectly pruned");
    }
}
}
int main(){try{
    objective_bound();
    for(const auto dimensions:{FloorplanPoint{100,100},FloorplanPoint{30,30}}) {
        auto in=fixture();auto observer=std::make_shared<FloorplanExperiment>();
        observer->initial_outline=dimensions;in.experiment=observer;
        std::map<bool,FloorplanAttemptObservation> first;
        observer->attempt_completed=[&](const auto& row){first.emplace(row.punch_free,row);};
        const auto result=build_floorplan(in);
        require(first.size()==2,"initial outline checked under both reservation policies");
        for(const auto& [policy,row]:first) {
            (void)policy;
            require(row.w==dimensions.first&&row.h==dimensions.second,"first candidate is the requested seed");
            require(row.packed==(dimensions.first==100),"seed is really packed, not presumed feasible");
        }
        if(dimensions.first==100)require(result.board_w*result.board_h<10000,"seed does not fix the final dimensions");
        else require(result.board_w>30||result.board_h>30,"rejected seed falls back to ordinary search");
        require(!in.spec->outline&&observer->initial_outline==dimensions,"source and seed stay immutable");
        const auto again=build_floorplan(in);
        require(result.board_w==again.board_w&&result.board_h==again.board_h&&
                result.accounting.quantization_engagements==again.accounting.quantization_engagements&&
                result.accounting.fallback_events==again.accounting.fallback_events,"seeded search is reproducible including actual work");
    }
    for(const auto dimensions:{FloorplanPoint{0,10},FloorplanPoint{-1,10},
        FloorplanPoint{std::numeric_limits<double>::infinity(),10},FloorplanPoint{1e300,1e300}}) {
        auto in=fixture();auto observer=std::make_shared<FloorplanExperiment>();observer->initial_outline=dimensions;in.experiment=observer;
        bool rejected=false;try{(void)build_floorplan(in);}catch(const FloorplanError&){rejected=true;}
        require(rejected,"invalid seed fails closed");
    }
    auto fixed=fixture();fixed.spec->outline={{100,100}};
    auto observer=std::make_shared<FloorplanExperiment>();observer->initial_outline={{80,80}};fixed.experiment=observer;
    bool rejected=false;try{(void)build_floorplan(fixed);}catch(const FloorplanError&){rejected=true;}
    require(rejected,"fixed outline and starting candidate cannot be confused");
    std::cout<<"PASS validated seed, failed-seed fallback, smaller search, isolation and reproducibility\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
