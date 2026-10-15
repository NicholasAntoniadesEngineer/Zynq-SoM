#include "schgen/pack_edges.hpp"
#include "../src/floorplan_internal.hpp"
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <map>
using namespace schgen;
namespace {
void require(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
using Poses=std::map<std::string,std::tuple<std::string,double,double>>;
Poses poses(const PackEdgesResult& result){
    Poses out;for(const auto& p:result.poses)require(out.emplace(p.name,std::make_tuple(p.edge,p.x,p.y)).second,"duplicate edge pose");
    return out;
}
}
int main(){try{
    const PackEdgesSpec spec{100,100,10,1.5,.3,20,3,.05,40,40,20,20};
    for(const std::string edge:{"N","E","S","W"}) {
        PackEdgeBlock a,b;a.name="a";b.name="b";
        a.w=b.w=10;a.h=b.h=5;a.assigned_edge=b.assigned_edge=edge;
        a.order_hint=0;b.order_hint=1;
        a.reach=b.reach={0,2,0,4};a.inset=b.inset={.5,.5,.5,.5};
        const auto fresh=pack_edges({a,b},{},spec);
        require(fresh.poses.size()==2,"two fresh edge blocks placed");
        const auto expected=poses(fresh);
        const auto& first=expected.at("a");const auto& second=expected.at("b");
        require(std::get<0>(first)==edge&&std::get<0>(second)==edge,"requested edge retained");
        const bool horizontal=edge=="N"||edge=="S";
        const double gap=horizontal?std::get<1>(second)-std::get<1>(first)-a.w:
                                    std::get<2>(second)-std::get<2>(first)-a.h;
        require(std::abs(gap-(horizontal?1.5:3.5))<1e-9,"actual edge determines directional fanout gap");
        for(const std::string stale:{"","N","E","S","W"}) {
            a.current_edge=stale;b.current_edge=stale;
            require(poses(pack_edges({a,b},{},spec))==expected,"prior edge must not alter current placement");
            b.current_edge=stale=="N"?"W":"N";
            require(poses(pack_edges({a,b},{},spec))==expected,"mixed prior edges must not alter placement");
        }
        a.overmold=b.overmold=true;
        const auto overmold=poses(pack_edges({a,b},{},spec));
        const double cable=horizontal?std::get<1>(overmold.at("b"))-std::get<1>(overmold.at("a"))-a.w:
                                     std::get<2>(overmold.at("b"))-std::get<2>(overmold.at("a"))-a.h;
        require(std::abs(cable-20)<1e-9,"overmold cable clearance retained");
    }
    // Three wide blocks: only the first fits north, so the others spill east.
    // Their stale north label must not select horizontal fanout on that edge.
    std::vector<PackEdgeBlock> blocks;
    for(const auto* name:{"a","b","c"}) {
        PackEdgeBlock b;b.name=name;b.w=80;b.h=5;b.assigned_edge="N";b.current_edge="N";
        b.reach={0,2,0,4};b.inset={.5,.5,.5,.5};blocks.push_back(b);
    }
    auto small=spec;small.board_w=102;small.board_h=50;
    const auto spilled=poses(pack_edges(blocks,{},small));
    require(spilled.size()==3&&std::get<0>(spilled.at("b"))=="E"&&std::get<0>(spilled.at("c"))=="E","spill witness exercises new edge");
    require(std::abs(std::get<2>(spilled.at("c"))-std::get<2>(spilled.at("b"))-5-3.5)<1e-9,
            "spilled pair uses destination edge's vertical fanout");
    QuantizationCounts rejected_counts;
    const auto overflow=pack_edges({blocks.front()},{},spec,&rejected_counts);
    require(overflow.poses.empty(),"body-only fit cannot consume reserved far-edge fanout margin");
    require(rejected_counts.at("pack_edge_pose_precision4dp")==1,"rejected rounded coordinate remains accounted");
    FloorplanInput input;input.som.w=10;input.som.h=10;
    // Forward clearance must survive 4dp pose rounding, including values just
    // either side of a decimal grid point. No epsilon in the safety predicate.
    for(const std::string edge:{"N","E","S","W"})for(int k=0;k<100;++k) {
        PackEdgeBlock a,b;a.name="a";b.name="b";a.assigned_edge=b.assigned_edge=edge;
        a.order_hint=0;b.order_hint=1;a.w=b.w=10.9881;a.h=b.h=10.9881;
        a.reach={0,1.4499,0,1.4499};
        auto grid=spec;grid.board_w=grid.board_h=300;grid.som_w=grid.som_h=0;
        grid.som_x=grid.som_y=110.3302+(2*10.9881+1.4499)/2+k*.00001;
        const auto packed=poses(pack_edges({a,b},{},grid));
        const double first=edge=="N"||edge=="S"?std::get<1>(packed.at("a")):std::get<2>(packed.at("a"));
        const double second=edge=="N"||edge=="S"?std::get<1>(packed.at("b")):std::get<2>(packed.at("b"));
        require(first+10.9881+1.4499<=second,"rounded edge poses preserve exact forward fanout clearance");
    }
    floorplan_detail::Engine engine(input);engine.board_size(1,1);
    FloorplanBlock block;block.name="jack";block.kind="edge";
    engine.plan.edge_blocks.push_back(block);engine.zbox["jack"]={10,5};engine.edge_of["jack"]="N";
    require(!engine.attempt_pack_impl(false),"unplaced fresh edge rejects without downstream invalid-edge exception");
    engine.plan.edge_blocks[0].edge="N";engine.plan.edge_blocks[0].x=20;engine.plan.edge_blocks[0].y=20;
    require(!engine.attempt_pack_impl(false),"unplaced stale edge cannot reuse an earlier pose");
    std::cout<<"PASS fresh, stale, mixed and spilled edge directions; cable gap retained\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
