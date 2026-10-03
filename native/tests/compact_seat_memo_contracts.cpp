#include "../src/pack_refine_internal.hpp"
#include "schgen/occupancy_precision.hpp"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <map>
#include <sstream>
#include <stdexcept>
#include <thread>

namespace {
using namespace schgen;
using namespace schgen::floorplan_detail;
void require(bool ok,const char* msg) {if(!ok) throw std::runtime_error(msg);}
template<class T> void append(std::string& s,const T& v) {
    s.append(reinterpret_cast<const char*>(&v),sizeof(v));
}
// Independent serialized complete varying key, not the production comparator.
std::string key(const SeatShapeCand& c) {
    std::string s;
    for(double v:{c.w,c.h,c.reach.w,c.reach.e,c.reach.n,c.reach.s,
        c.inset.w,c.inset.e,c.inset.n,c.inset.s,c.win_x0,c.win_x1,c.win_y0,c.win_y1}) append(s,v);
    append(s,c.mask); append(s,c.comps.size());
    for(const auto& p:c.comps) {append(s,p.dx);append(s,p.dy);append(s,p.w);append(s,p.h);append(s,p.mask);}
    return s;
}
std::string signature(const std::vector<SeatShapeHit>& hits) {
    std::ostringstream s; s<<std::hexfloat;
    for(const auto& h:hits) {
        s<<h.side<<':'<<h.index<<':'<<h.x<<':'<<h.y<<':'<<h.w<<':'<<h.h<<':'<<h.dist_key;
        for(const auto& v:{h.reach,h.inset}) s<<':'<<v.w<<':'<<v.e<<':'<<v.n<<':'<<v.s;
        for(const auto& c:h.comps) s<<'/'<<c.dx<<':'<<c.dy<<':'<<c.w<<':'<<c.h<<':'<<c.mask;
        s<<'\n';
    }
    return s.str();
}
SeatShapeCand shape(int i) {return {i,3,2,{},{},1,i%2?"B":"A",{},-30,60,-30,60};}
QuantizationCounts expected(const Occupancy& occ,const std::vector<SeatShapeCand>& c,double ax,double ay) {
    QuantizationCounts counts;
    std::map<std::string,std::optional<Pose>> seen;
    for(const auto& v:c) {
        if(v.w>28||v.h>28) continue;
        const auto k=key(v);
        auto it=seen.find(k);
        if(it==seen.end()) it=seen.emplace(k,occ.place_near(ax,ay,v.w,v.h,v.reach,v.inset,
            v.mask,v.comps,v.win_x0,v.win_x1,v.win_y0,v.win_y1,&counts)).first;
        if(it->second) (void)occupancy_shape_key4dp(std::fabs(it->second->x+v.w/2-ax)+
                                                  std::fabs(it->second->y+v.h/2-ay),&counts);
    }
    return counts;
}
void check(const Occupancy& occ,const std::vector<SeatShapeCand>& c,double ax=8,double ay=8) {
    QuantizationCounts old,now,again;
    const auto reference=seat_shape_candidates(occ,ax,ay,c,30,30,1,&old);
    // Legacy/default side selection remains nearest distance, then stable index,
    // in first-successful-side order, with every offered query still executed.
    std::vector<SeatShapeHit> sides;
    for(const auto& h:reference) {
        auto it=std::find_if(sides.begin(),sides.end(),[&](const auto& prior){return prior.side==h.side;});
        if(it==sides.end()) sides.push_back(h);
        else if(h.dist_key<it->dist_key||(h.dist_key==it->dist_key&&h.index<it->index)) *it=h;
    }
    QuantizationCounts default_counts;
    require(signature(sides)==signature(seat_shape_sides(occ,ax,ay,c,30,30,1,&default_counts))&&default_counts==old,
            "legacy/default side selection or receipts changed");
    const auto hits=seat_shape_candidates_on_current_board(occ,ax,ay,c,30,30,1,&now);
    require(signature(reference)==signature(hits),"ordered full hits changed");
    require(now==expected(occ,c,ax,ay),"receipts differ from actual unique queries plus every successful shape scalar");
    require(signature(hits)==signature(seat_shape_candidates_on_current_board(occ,ax,ay,c,30,30,1,nullptr)),"null sink changed hits");
    require(signature(hits)==signature(seat_shape_candidates_on_current_board(occ,ax,ay,c,30,30,1,&again))&&now==again,"cross-invocation result reuse");
    std::map<std::string,bool> unique;
    for(const auto& v:c) unique[key(v)]=true;
    if(unique.size()==c.size()) require(old==now,"nonduplicate receipts changed");
}
void fields() {
    auto a=shape(0); a.comps={{0,1,2,3,1},{4,5,6,7,2}};
    auto b=a; b.index=99; b.side="other";
    require(same_query_geometry(a,b),"identity incorrectly part of geometry key");
    auto different=[&](const SeatShapeCand& c){require(!same_query_geometry(a,c)&&key(a)!=key(c),"omitted key field");};
    for(auto f:{&SeatShapeCand::w,&SeatShapeCand::h,&SeatShapeCand::win_x0,&SeatShapeCand::win_x1,&SeatShapeCand::win_y0,&SeatShapeCand::win_y1}) {b=a;b.*f+=1;different(b);}
    for(auto f:{&Halo::w,&Halo::e,&Halo::n,&Halo::s}) {b=a;b.reach.*f+=1;different(b);b=a;b.inset.*f+=1;different(b);}
    for(std::size_t i=0;i<a.comps.size();++i) {
        for(auto f:{&Comp::dx,&Comp::dy,&Comp::w,&Comp::h}) {b=a;b.comps[i].*f+=1;different(b);}
        b=a;++b.comps[i].mask;different(b);
    }
    b=a;++b.mask;different(b);b=a;b.comps.pop_back();different(b);
    b=a;std::swap(b.comps[0],b.comps[1]);different(b);
    b=a;b.comps[0].dx=-0.0;different(b);
    require(cacheable_query_geometry(a),"valid geometry not cacheable");
    for(double bad:{std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity(),
                    std::numeric_limits<double>::quiet_NaN()}) {
        for(auto f:{&SeatShapeCand::w,&SeatShapeCand::h,&SeatShapeCand::win_x0,&SeatShapeCand::win_x1,&SeatShapeCand::win_y0,&SeatShapeCand::win_y1}) {
            b=a;b.*f=bad;require(!cacheable_query_geometry(b),"nonfinite geometry cacheable");
        }
        for(auto f:{&Halo::w,&Halo::e,&Halo::n,&Halo::s}) {
            b=a;b.reach.*f=bad;require(!cacheable_query_geometry(b),"nonfinite reach cacheable");
            b=a;b.inset.*f=bad;require(!cacheable_query_geometry(b),"nonfinite inset cacheable");
        }
        for(auto f:{&Comp::dx,&Comp::dy,&Comp::w,&Comp::h}) {
            b=a;b.comps[1].*f=bad;require(!cacheable_query_geometry(b),"nonfinite child cacheable");
        }
    }
    b=a;b.w=-1;require(!cacheable_query_geometry(b),"negative width cacheable");
    b=a;b.win_x1=b.win_x0-1;require(!cacheable_query_geometry(b),"reversed window cacheable");
}
void run() {
    fields();
    Occupancy occ(30,30,1,8,2,1,.05);
    auto a=shape(0),b=a;b.index=1;b.side="other";
    check(occ,{a,b});
    QuantizationCounts single,repeated;
    (void)seat_shape_candidates_on_current_board(occ,8,8,{a},30,30,1,&single);
    const auto hits=seat_shape_candidates_on_current_board(occ,8,8,{a,b},30,30,1,&repeated);
    require(hits.size()==2&&hits[0].index==0&&hits[1].index==1,"lost estimator alternatives");
    checked_quantization_add(single,"occupancy_shape_key4dp");
    require(single==repeated,"duplicate hit executed or fabricated query receipts");
    auto miss=a;miss.win_x0=100;miss.win_x1=101;
    check(occ,{miss,miss});
    auto oversized=a;oversized.w=40;check(occ,{oversized,oversized,a});
    for(int n=0;n<40;++n) {
        std::vector<SeatShapeCand> c;
        for(int j=0;j<8;++j) {
            auto v=shape(j);v.w+=j%3;v.mask=1+j%3;
            v.comps={{-.25,double(n%3),.5,1,2}};
            c.push_back(v);v.index+=20;v.side="alias";c.push_back(v);
        }
        check(occ,c,3+n%20,4+n%19);
    }
    occ.add(1,1,20,20,{},{},1,{});check(occ,{a,b});
    auto copy=occ;copy.remove(1,1,20,20,{},{},1,{});check(copy,{a,b});check(occ,{a,b},22,22);
    // Public/default path still executes every offered query and retains its
    // board override behavior; compare duplicate and distinct-label adapters.
    QuantizationCounts public_counts;
    (void)seat_shape_candidates(copy,8,8,{a,b},30,30,1,&public_counts);
    require(public_counts.at("occupancy_cell_index")==2*repeated.at("occupancy_cell_index"),"public path memoized");
    QuantizationCounts overflow{{"occupancy_cell_index",std::numeric_limits<std::size_t>::max()}};
    auto baseline=overflow;std::string e1,e2;
    try{(void)seat_shape_candidates(copy,8,8,{a},30,30,1,&baseline);}catch(const std::exception& e){e1=e.what();}
    try{(void)seat_shape_candidates_on_current_board(copy,8,8,{a,b},30,30,1,&overflow);}catch(const std::exception& e){e2=e.what();}
    require(!e1.empty()&&e1==e2&&baseline==overflow,"failed first-query prefix changed");
    // The first identical query completes, but the next cannot fit the current
    // counter budget. A memo hit must not hide that actual overflow prefix.
    QuantizationCounts once;
    (void)seat_shape_candidates(copy,8,8,{a},30,30,1,&once);
    for(const auto* name:{"occupancy_axis_count","occupancy_frontier_key1dp","occupancy_cell_index","occupancy_shape_key4dp"}) {
        baseline={{name,std::numeric_limits<std::size_t>::max()-once.at(name)}};overflow=baseline;e1.clear();e2.clear();
        try{(void)seat_shape_candidates(copy,8,8,{a,b},30,30,1,&baseline);}catch(const std::overflow_error& e){e1=e.what();}
        try{(void)seat_shape_candidates_on_current_board(copy,8,8,{a,b},30,30,1,&overflow);}catch(const std::overflow_error& e){e2=e.what();}
        require(!e1.empty()&&e1==e2&&baseline==overflow,"memo suppressed current overflow or prefix");
    }
    auto malformed=a;malformed.win_x0=std::numeric_limits<double>::quiet_NaN();
    baseline.clear();overflow.clear();
    const auto old_malformed=seat_shape_candidates(copy,8,8,{malformed,malformed},30,30,1,&baseline);
    const auto new_malformed=seat_shape_candidates_on_current_board(copy,8,8,{malformed,malformed},30,30,1,&overflow);
    require(signature(old_malformed)==signature(new_malformed)&&baseline==overflow,"malformed miss reused");
    QuantizationCounts c1,c2;
    std::thread t1([&]{(void)seat_shape_candidates_on_current_board(copy,8,8,{a,b},30,30,1,&c1);});
    std::thread t2([&]{(void)seat_shape_candidates_on_current_board(copy,8,8,{a,b},30,30,1,&c2);});
    t1.join();t2.join();require(c1==c2&&c1==repeated,"thread/invocation isolation");
}
}
int main(){try{run();std::cout<<"PASS compact seat memo: full hits, exact actual receipts, complete geometry, misses, mutations, overflow, null, threads\n";}
catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
