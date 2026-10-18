// Diagnostic of the current centroid proxy, not a hardware acceptance test.
#include "schgen/pcb_placement_gates.hpp"
#include "schgen/legalize.hpp"
#include <cmath>
#include <iostream>
#include <stdexcept>
using namespace schgen;
int main(){try {
    PcbPlacementGatePolicy policy;
    policy.wired_sheets={"source"};policy.project_zones={"source","load"};
    policy.contracts["source"]=parse_json_text(R"({"contract":"placement/v2",
      "roles":{"U1":"buck_ic","C1":"cout_bulk","TP1":"testpoint"},
      "external":{"downstream":"load","output_roles":["cout_bulk"]}})");
    policy.ref_maps["source"]={{"U1","U1"},{"C1","C1"},{"TP1","TP1"}};
    int cases=0;
    for(bool flip_x:{false,true})for(bool flip_y:{false,true}) {
        const auto point=[&](double x,double y){return std::make_pair(flip_x?60-x:x,flip_y?60-y:y);};
        const auto regulator=point(10,10),output=point(12,10),load=point(20,20);
        for(bool moved:{false,true}) {
            PcbCheckModel model;model.board_w=model.board_h=60;
            const auto append=[&](const char* ref,const char* sheet,std::pair<double,double> p){
                PcbCheckInstance i;i.ref=ref;i.sheet=sheet;i.x=p.first;i.y=p.second;
                model.insts.push_back(i);
            };
            append("U1","source",regulator);append("C1","source",output);
            append("TP1","source",point(10,moved?30:11));append("LOAD","load",load);
            // No footprint geometry is supplied: this deliberately invokes
            // only the centroid flow gate, never claims board qualification.
            const auto result=check_pcb_placement_flow(PcbCheckInput(model),policy);
            if(result.facing_checked!=1||result.facing_fail!=(moved?1:0)||result.ok==moved)
                throw std::runtime_error("current centroid sensitivity witness changed");
            const auto anchored=facing_dot(regulator.first,regulator.second,
                output.first,output.second,load.first,load.second);
            if(anchored.first<=0||std::hypot(output.first-load.first,output.second-load.second)!=std::sqrt(164.))
                throw std::runtime_error("critical geometry changed");
            std::cout<<"flip_x="<<flip_x<<" flip_y="<<flip_y<<" testpoint_moved="<<moved
                     <<" facing_fail="<<result.facing_fail<<" regulator_anchored_dot="<<anchored.first
                     <<" output_load_distance="<<std::sqrt(164.)<<" scope=centroid_gate_only\n";
            ++cases;
        }
    }
    std::cout<<"cases="<<cases<<" nonoutput_movement_changes_verdict=1 critical_geometry_unchanged=1\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
