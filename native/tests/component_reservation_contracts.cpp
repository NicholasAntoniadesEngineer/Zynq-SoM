#include "schgen/floorplan.hpp"
#include <iostream>
#include <stdexcept>
using namespace schgen;
void demand(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
int main(){try {
    const std::vector<Comp> a{{0,0,2,2,1},{8,0,2,2,1}};
    const std::vector<Comp> b{{0,3,2,2,1},{8,3,2,2,1}};
    Occupancy grid(15,8,.3,2,2,.5,.05);
    grid.add(1,1,10,6,{},{},0,a);
    demand(grid.fits_exhaustive(2,1,10,6,{},{},0,b)&&grid.fits_hashed(2,1,10,6,{},{},0,b),
           "interlocking component groups rejected");
    demand(!grid.fits_exhaustive(1,1,10,6,{},{},0,a)&&!grid.fits_hashed(1,1,10,6,{},{},0,a),
           "same-face component collision escaped parent-zero representation");
    auto bottom=a;for(auto& c:bottom)c.mask=2;
    demand(grid.fits_hashed(1,1,10,6,{},{},0,bottom),"disjoint physical faces blocked");
    bottom.front().mask=3;
    demand(!grid.fits_hashed(1,1,10,6,{},{},0,bottom),"through-hole occupancy lost");
    auto halo=b;for(auto& c:halo)c.reach.n=2;
    demand(!grid.fits_hashed(2,1,10,6,{},{},0,halo),"component fanout lost");
    grid.remove(1,1,10,6,{},{},0,a);
    demand(grid.fits_hashed(1,1,10,6,{},{},0,a),"component removal left stale occupancy");
    FloorplanLegalizeInput in;in.board_w=15;in.board_h=8;in.clear=.3;in.compact=true;
    in.primary_fanout["a"]={{},{},0,1,a,true};
    in.primary_fanout["b"]={{},{},0,1,b,true};
    const std::vector<FloorplanLegalizeVar> seed{{"a",10,6,{1,1},1,1},{"b",10,6,{2,1},2,1}};
    auto vars=seed;std::vector<std::string> log;QuantizationCounts counts;
    demand(floorplan_legalize_compact_accounted(in,vars,log,counts),"legalizer cannot retain interlocking reservations");
    auto repeated=seed;std::vector<std::string> repeated_log;QuantizationCounts repeated_counts;
    demand(floorplan_legalize_compact_accounted(in,repeated,repeated_log,repeated_counts)&&
           log==repeated_log&&counts==repeated_counts,"component solve/accounting is not reproducible");
    for(std::size_t i=0;i<vars.size();++i)
        demand(vars[i].x==repeated[i].x&&vars[i].y==repeated[i].y,"component poses are not reproducible");
    Occupancy verify(15,8,.3,2,2,.5,.05);
    verify.add(vars[0].x,vars[0].y,10,6,{},{},0,a);
    demand(verify.fits_exhaustive(vars[1].x,vars[1].y,10,6,{},{},0,b),"legalizer accepted physical overlap");
    auto solid=in;
    solid.primary_fanout["a"].children=std::vector<Comp>{{0,0,10,6,1}};
    solid.primary_fanout["b"].children=std::vector<Comp>{{0,0,10,6,1}};
    vars=seed;demand(!floorplan_legalize_compact(solid,vars,log),"impossible same-face bodies accepted");
    demand(vars[0].x==seed[0].x&&vars[0].y==seed[0].y&&
           vars[1].x==seed[1].x&&vars[1].y==seed[1].y,"failed physical solve mutated incumbent");
    solid.primary_fanout["b"].children->front().mask=2;
    solid.primary_fanout["b"].occupied_mask=2;
    vars=seed;demand(floorplan_legalize_compact(solid,vars,log),"independent opposite-face bodies blocked");
    solid.primary_fanout["b"].children->front().mask=3;
    solid.primary_fanout["b"].occupied_mask=3;
    vars=seed;demand(!floorplan_legalize_compact(solid,vars,log),"through-hole body passed through other face");
    // No implicit reinterpretation of malformed or unknown logical bodies.
    for(int defect=0;defect<6;++defect) {
        auto invalid=in;auto& body=invalid.primary_fanout.at("a");
        if(defect==0)body.component_only=false;
        if(defect==1)body.children.reset();
        if(defect==2)body.children->clear();
        if(defect==3)body.occupied_mask=2;
        if(defect==4)body.reach.n=1;
        if(defect==5)body.children->front().dx=-1;
        bool rejected=false;vars=seed;
        try{(void)floorplan_legalize_compact(invalid,vars,log);}catch(const std::exception&){rejected=true;}
        demand(rejected,"incomplete physical reservations accepted");
    }
    auto blocked=in;blocked.fixed_rects={{"keepout",{0,0,15,8}}};blocked.primary_fanout["keepout"]={};
    vars=seed;demand(!floorplan_legalize_compact(blocked,vars,log),"logical keepout bypassed");
    demand(vars[0].x==seed[0].x&&vars[1].x==seed[1].x,"failed solve mutated incumbent");
    std::cout<<"component-only occupancy and legalization contracts PASS\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
