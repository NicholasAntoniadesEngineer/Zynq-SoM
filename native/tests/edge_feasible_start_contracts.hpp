#pragma once
#include "edge_feasible_start_internal.hpp"
#include "schgen/pack_edges.hpp"
#include <limits>

namespace edge_feasible_start_test {
template<class Require> void run(Require require){
    using namespace schgen;
    using schgen::floorplan_detail::edge_collision_interval;
    using schgen::floorplan_detail::nearest_feasible_edge_start;
    using Intervals=std::vector<std::pair<double,double>>;
    require(nearest_feasible_edge_start(4,0,10,{})==4,"unblocked preferred start");
    require(nearest_feasible_edge_start(-1,0,10,{})==0,"preferred start clamps to domain");
    require(nearest_feasible_edge_start(2,0,4,{{1,3}})==1,"equal clearance boundaries choose low");
    require(nearest_feasible_edge_start(2.75,0,4,{{1,3}})==3,"nearest upper clearance boundary");
    require(nearest_feasible_edge_start(1.5,0,4,{{-1,2},{2,5}})==2,"isolated legal point between open collisions");
    require(nearest_feasible_edge_start(2,2,2,{{0,2},{2,4}})==2,"zero-width legal domain");
    require(!nearest_feasible_edge_start(2,0,4,{{-1,5}}),"fully blocked domain rejects");
    require(nearest_feasible_edge_start(2,0,4,{{2,2}})==2,"empty collision interval blocks nothing");
    const auto largest=std::numeric_limits<double>::max();
    require(nearest_feasible_edge_start(largest/2,-largest,largest,{{-largest,largest}})==largest,
        "overflowing far distance cannot win");
    const auto tiny=std::numeric_limits<double>::denorm_min();
    require(nearest_feasible_edge_start(0,-tiny,tiny,{{-tiny,tiny}})==-tiny,"subnormal symmetric tie");
    // Exact dyadic exhaustive oracle: all interval endpoints and preferred
    // positions are on this grid, so a nearest feasible point must be too.
    // Independent brute force visits every legal point, not solver candidates.
    for(int a=-4;a<=4;++a)for(int b=a;b<=4;++b)
    for(int c=-4;c<=4;++c)for(int d=c;d<=4;++d)
    for(int target=-5;target<=5;++target){
        std::optional<double> expected;int distance=100;
        for(int point=-3;point<=3;++point){
            if((a<point&&point<b)||(c<point&&point<d))continue;
            const int delta=std::abs(point-target);
            if(delta<distance){distance=delta;expected=point/2.;}
        }
        const Intervals gaps{{a/2.,b/2.},{c/2.,d/2.}};
        require(nearest_feasible_edge_start(target/2.,-1.5,1.5,gaps)==expected,
                "nearest feasible start differs from exhaustive dyadic oracle");
        require(nearest_feasible_edge_start(target/2.,-1.5,1.5,{gaps[1],gaps[0]})==expected,
                "collision order changed optimum");
    }
    for(const auto& gaps:Intervals{{2,1},{0,std::numeric_limits<double>::infinity()}}){
        bool rejected=false;try{(void)nearest_feasible_edge_start(1,0,2,{gaps});}
        catch(const std::invalid_argument&){rejected=true;}require(rejected,"invalid collision interval accepted");
    }
    bool rejected=false;try{(void)nearest_feasible_edge_start(std::numeric_limits<double>::quiet_NaN(),0,1,{});}
    catch(const std::invalid_argument&){rejected=true;}require(rejected,"nonfinite target accepted");
    for(bool horizontal:{false,true})for(int variant=0;variant<8;++variant)
    for(int transverse=-4;transverse<=4;++transverse) {
        EdgeFanoutBlock moving{0,0,1,1.5,{.5,1,1.5,2},{.25,.5,.75,1},'N'};
        EdgeFanoutBlock fixed{1,1,2,1,{1.5,.5,2,1},{.5,.25,1,.75},'W'};
        if(variant&1){moving.reach={};fixed.reach={};}
        if(variant&2){moving.inset={};fixed.inset={};}
        if(variant&4){moving.w=.5;moving.h=2;}
        (horizontal?moving.y:moving.x)=transverse/2.;
        const auto interval=edge_collision_interval(moving,fixed,horizontal,.25);
        for(int position=-24;position<=32;++position){
            (horizontal?moving.x:moving.y)=position/4.;
            const bool collides=interval&&interval->first<position/4.&&position/4.<interval->second;
            require(collides!=cross_edge_fanout_hold({moving,fixed},.25),"interval disagrees with independent physical clearance predicate");
        }
    }
    // A north connector forces the west run away from its preferred start.
    // This is initial constrained optimisation, not a translated repair trial.
    PackEdgesSpec spec{30,30,2,1.5,.5,1,1,1,0,0,20,20};
    PackEdgeBlock north; north.name="north";north.w=10;north.h=9;north.assigned_edge="N";
    north.order_hint=0;north.j_aff={{"north",1}};
    PackEdgeBlock west;west.name="west";west.w=9;west.h=5;west.assigned_edge="W";
    west.order_hint=0;west.j_aff={{"west",1}};
    const std::vector<PackEdgeJack> jacks{{"north",10,0},{"west",0,10.5}};
    const std::vector<Box4> keepouts;
    const auto unconstrained=pack_edges({north,west},jacks,spec);
    const auto constrained=pack_edges({north,west},jacks,spec,nullptr,&keepouts);
    require(unconstrained.poses.size()==2&&unconstrained.poses[1].y==8,"test must exercise colliding preferred west pose");
    require(constrained.poses.size()==2&&constrained.poses[1].y==11&&constrained.feasibility_runs==2&&
        constrained.feasibility_intervals==1&&constrained.feasibility_rejections==0,"initial edge solve did not select nearest safe start");
    require(cross_edge_fanout_hold({{constrained.poses[0].x,constrained.poses[0].y,10,9,{},{},'N'},
        {constrained.poses[1].x,constrained.poses[1].y,9,5,{},{},'W'}},.5),"initial solve violates actual geometry");
    const std::vector<Box4> blocked{{0,0,30,30}};
    const auto impossible=pack_edges({north,west},jacks,spec,nullptr,&blocked);
    require(impossible.poses.empty()&&impossible.feasibility_rejections==1,"blocked initial run must fail closed");
    require(impossible.rejected_edge=="N"&&impossible.rejection_reason=="obstacle_intervals"&&
        impossible.feasible_start_low<=impossible.feasible_start_high,"blocked domain rejection misreported");
    require(constrained.rejection_reason.empty()&&constrained.rejected_edge.empty(),"successful run reported a rejection");
    auto oversized_reach=north;oversized_reach.reach.w=100;
    const auto no_domain=pack_edges({oversized_reach},{},spec,nullptr,&keepouts);
    require(no_domain.rejected_edge=="N"&&no_domain.rejection_reason=="run_span"&&
        no_domain.feasible_start_low>no_domain.feasible_start_high,"run including endpoint reach exceeds domain");
    for(char edge:{'N','E','S','W'}) {
        const bool horizontal=edge=='N'||edge=='S';
        PackEdgeBlock block;block.name="single";block.assigned_edge=std::string(1,edge);
        block.w=horizontal?10:5;block.h=horizontal?5:10;
        const double perpendicular=edge=='N'||edge=='W'?1.5:23.5;
        const std::vector<Box4> obstacles{horizontal?Box4{4,perpendicular,9,perpendicular+5}:Box4{perpendicular,4,perpendicular+5,9}};
        const auto legal=pack_edges({block},{},spec,nullptr,&obstacles);
        require(legal.poses.size()==1&&(horizontal?legal.poses[0].x:legal.poses[0].y)==9,
            "initial keepout avoidance failed on an edge orientation");
        auto fractional=obstacles;
        (horizontal?fractional[0].x1:fractional[0].y1)=9.00001;
        const auto rounded=pack_edges({block},{},spec,nullptr,&fractional);
        require(rounded.poses.empty()&&rounded.feasibility_rejections==1,
            "rounded-down unsafe clearance boundary must fail closed");
        require(rounded.rejected_edge==std::string(1,edge)&&rounded.rejection_reason=="rounded_geometry",
            "rounded rejection lost its edge or physical-check reason");
    }
    for(const auto& domain:Intervals{{2,1},{0,std::numeric_limits<double>::infinity()}}){
        bool threw=false;try{(void)nearest_feasible_edge_start(0,domain.first,domain.second,{});}
        catch(const std::invalid_argument&){threw=true;}require(threw,"invalid domain accepted");
    }
    for(int mode=0;mode<3;++mode){
        EdgeFanoutBlock moving{0,0,1,1,{},{},'N'},fixed{0,0,1,1,{},{},'W'};
        if(mode==0)moving.w=0;
        if(mode==1)fixed.reach.w=std::numeric_limits<double>::quiet_NaN();
        bool threw=false;try{(void)edge_collision_interval(moving,fixed,true,mode==2?-1:0);}
        catch(const std::invalid_argument&){threw=true;}require(threw,"invalid collision geometry accepted");
    }
}
}
