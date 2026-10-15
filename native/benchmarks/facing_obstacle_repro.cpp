// Diagnostic known-feasible miss at 9d506722; not a passing acceptance test.
// Compile against libschgen_core.a with native/include and native/src includes.
#include "floorplan_internal.hpp"
#include <iostream>
using namespace schgen;
int main() {
    FloorplanLegalizeInput in;
    in.board_w=in.board_h=60;in.clear=.3;in.joint_separation_states=64;
    in.metrics["source"].offsets={{"out",2,2},{"in",0,0}};
    in.metrics["target"].offsets={{"p",1,1}};
    in.fixed_poses["target"]={30,30};
    in.fixed_rects={{"target",{30,30,32,32}},
                    {"strip",{0,0,33,28}},{"column",{0,28,28,60}}};
    FloorplanTerm term;term.kind="facing";term.subject="source";
    term.target_raw="target";term.enforced=true;
    term.require_positive_facing=true;term.out_refs={"out"};in.index.hard={term};
    std::vector<FloorplanLegalizeVar> vars{{"source",2,2,{40,40},40,40}};
    std::vector<std::string> log;
    const bool accepted=floorplan_legalize_compact(in,vars,log);
    // Independent witness: board enclosure, all obstacle clearances, then the
    // exact public facing evaluation. Direction (1,1) dot (target-source)=16.
    const double x=34,y=10,w=2,h=2;
    if(x<in.clear||y<in.clear||x+w>in.board_w-in.clear||y+h>in.board_h-in.clear)return 2;
    for(const auto& [name,b]:in.fixed_rects) {
        (void)name;
        if(!(x>=b.x1+in.clear||x+w+in.clear<=b.x0||
             y>=b.y1+in.clear||y+h+in.clear<=b.y0))return 3;
    }
    if((30-x)+(30-y)<=0)return 4;
    auto poses=in.fixed_poses;poses["source"]={x,y};
    if(!floorplan_evaluate_terms(in,poses).front().ok)return 5;
    std::cout<<"accepted="<<accepted<<" independently_valid_witness=34,10\n";
    if(accepted) {
        const auto& v=vars.front();
        if(v.x<in.clear||v.y<in.clear||v.x+v.w>in.board_w-in.clear||v.y+v.h>in.board_h-in.clear)return 6;
        for(const auto& [name,b]:in.fixed_rects) {
            (void)name;
            if(!(v.x>=b.x1+in.clear||v.x+v.w+in.clear<=b.x0||
                 v.y>=b.y1+in.clear||v.y+v.h+in.clear<=b.y0))return 7;
        }
        poses["source"]={v.x,v.y};
        if((30-v.x)+(30-v.y)<=0||!floorplan_evaluate_terms(in,poses).front().ok)return 8;
        std::cout<<"independently_checked_solution="<<v.x<<","<<v.y<<'\n';
    } else if(vars.front().x!=40||vars.front().y!=40)return 9;
    for(const auto& line:log)std::cout<<line<<'\n';
    // A known feasible miss must remain a diagnostic failure, not green proof.
    return accepted?0:1;
}
