#include "schgen/pack_refine.hpp"
#include "../src/floorplan_internal.hpp"
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace schgen;
static void require(bool ok,const char* message) {if(!ok)throw std::runtime_error(message);}
template<class F> static void rejects(F f) {bool rejected=false;try {f();}catch(const std::exception&){rejected=true;}require(rejected,"malformed area accepted");}
int main() {try {
    // Exercise the actual sizing adapter in BOTH search modes. Three 8x8
    // primary bodies fit on an 8x16 board: core/top at y=0, top and bottom
    // blocks at y=8. A one-face sum (192) wrongly rejects its area of 128.
    for(bool compact:{false,true})for(bool free:{false,true}) {
        FloorplanInput input;input.som.w=8;input.som.h=8;input.compact_search=compact;
        floorplan_detail::Engine e(input);
        for(const auto& name:{"top_block","bottom_block"}) {
            FloorplanBlock b;b.name=name;b.kind="interior";e.plan.interior_blocks.push_back(b);
            e.zbox[name]={8,8};
            for(auto& sets:e.shape_sets)sets[name].push_back({8,8,{},{},std::string(name)=="top_block"?"top":"bottom",{}});
        }
        require(e.packing_area_bound(free)==128,"normal and compact sizing must use face-aware bound");
        Occupancy witness(8,16,0,2,0,1,.05);
        witness.add(0,0,8,8,{},{},free?1:3,{});
        witness.add(0,8,8,8,{},{},1,{});
        require(witness.fits_exhaustive(0,8,8,8,{},{},2,{}),"two-face area counterexample is not physically packable");
        FloorplanBlock edge;edge.name="edge";edge.kind="edge";e.plan.edge_blocks.push_back(edge);e.zbox["edge"]={8,8};
        require(e.packing_area_bound(free)==192,"edge reservation omitted from sizing bound");
        for(auto& sets:e.shape_sets)sets.at("top_block").front().side="bottom";
        require(e.packing_area_bound(free)==(free?128:256),"core/edge punch policy lost in area bound");
    }
    require(packing_area_lower_bound({{{20,1}},{{20,2}}},1,2)==20,"opposed faces must overlap in projection");
    require(packing_area_lower_bound({{{20,1}},{{20,1}}},1,2)==40,"same-face loads must accumulate");
    require(packing_area_lower_bound({{{20,3}},{{20,1},{20,2}}},1,2)==30,"pierced body consumes both faces");
    require(packing_area_lower_bound({{{20,1},{8,2}},{{20,1},{8,2}}},1,2)==8,"variants require independent necessary bounds");
    require(packing_area_lower_bound({},1,2)==0,"empty required set");
    // Enumerate every assignment of small two-option instances. A necessary
    // bound may never exceed the actual per-face load of any assignment.
    for(int a=1;a<=5;++a)for(int b=1;b<=5;++b)for(int m=1;m<=3;++m) {
        const std::vector<std::vector<PackingAreaOption>> rows{
            {{double(a),1},{double(b),2}},{{double(b),m},{double(a),3}}};
        const auto bound=packing_area_lower_bound(rows,1,2);
        for(const auto& x:rows[0])for(const auto& y:rows[1]) {
            const double top=((x.mask&1)?x.area:0)+((y.mask&1)?y.area:0);
            const double bottom=((x.mask&2)?x.area:0)+((y.mask&2)?y.area:0);
            require(bound<=std::max(top,bottom),"lower bound eliminates a legal face assignment");
        }
    }
    rejects([]{packing_area_lower_bound({{}},1,2);});
    rejects([]{packing_area_lower_bound({{{-1,1}}},1,2);});
    rejects([]{packing_area_lower_bound({{{1,4}}},1,2);});
    rejects([]{packing_area_lower_bound({{{std::numeric_limits<double>::quiet_NaN(),1}}},1,2);});
    rejects([]{packing_area_lower_bound({{{1,1}}},1,1);});
    Occupancy occupancy(20,20,0,2,0,1,.05);
    std::vector<SeatShapeCand> candidates;
    for(int i=0;i<3;++i) {
        SeatShapeCand c;c.index=i;c.w=i+2;c.h=2;c.mask=1;c.side="top";
        c.win_x0=0;c.win_y0=0;c.win_x1=20;c.win_y1=20;candidates.push_back(c);
    }
    const auto legacy=seat_shape_sides(occupancy,10,10,candidates,20,20,0);
    const auto expanded=seat_shape_candidates(occupancy,10,10,candidates,20,20,0);
    require(legacy.size()==1,"default face shortlist changed");
    require(expanded.size()==3,"legal same-face variants prematurely pruned");
    for(std::size_t i=0;i<expanded.size();++i)require(expanded[i].index==int(i),"candidate order not deterministic");
    const auto replay=seat_shape_candidates(occupancy,10,10,candidates,20,20,0);
    for(std::size_t i=0;i<replay.size();++i)require(replay[i].x==expanded[i].x&&replay[i].y==expanded[i].y,"candidate replay changed");
    auto oversized=candidates.front();oversized.index=3;oversized.w=21;
    candidates.push_back(oversized);
    const auto legal=seat_shape_candidates(occupancy,10,10,candidates,20,20,0);
    require(legal.size()==expanded.size(),"expanded search accepted an oversized shape");
    for(std::size_t i=0;i<legal.size();++i)
        require(legal[i].index==expanded[i].index&&legal[i].x==expanded[i].x&&legal[i].y==expanded[i].y,
                "illegal candidate changed legal shortlist");
    std::cout<<"compact search lower-bound and candidate retention contracts PASS\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
