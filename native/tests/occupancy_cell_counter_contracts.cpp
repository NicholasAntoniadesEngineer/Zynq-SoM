#include "schgen/occupancy.hpp"
#include "schgen/occupancy_precision.hpp"
#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <iostream>
#include <limits>
#include <optional>
#include <stdexcept>
#include <thread>
#include <type_traits>
#include <tuple>

// Compile only occupancy_precision.cpp with function-entry instrumentation;
// this test and occupancy.cpp stay separate, uninstrumented translation units.
namespace {
using namespace schgen;
thread_local bool observing=false;
thread_local std::array<std::size_t,6> entries{};
const char* names[]={"occupancy_component_precision4dp","occupancy_reach_precision4dp",
    "occupancy_frontier_key1dp","occupancy_shape_key4dp","occupancy_cell_index","occupancy_axis_count"};
void require(bool p,const char* why) {if(!p)throw std::runtime_error(why);}
static_assert(!std::is_copy_constructible_v<OccupancyCellSlot>);
static_assert(!std::is_move_constructible_v<OccupancyCellSlot>);

// Frozen original scalar: compare results, exception class/message and precise
// failed prefixes independently of the new counter view/slot implementation.
int reference(double coordinate,double bucket,QuantizationCounts* counts) {
    if(counts)checked_quantization_add(*counts,"occupancy_cell_index");
    if(!std::isfinite(coordinate)||!std::isfinite(bucket)||bucket==0)
        throw std::invalid_argument("occupancy_cell_index: finite coordinate and finite nonzero bucket required");
    const double cell=std::floor(coordinate/bucket);
    if(!std::isfinite(cell)||cell<std::numeric_limits<int>::min()||cell>std::numeric_limits<int>::max())
        throw std::out_of_range("occupancy_cell_index: floored quotient must fit int");
    return static_cast<int>(cell);
}
struct Result {
    int value=0;std::string kind,message;
    bool operator==(const Result& b)const{return value==b.value&&kind==b.kind&&message==b.message;}
};
template<class F> Result outcome(F action) {
    Result r;
    try{r.value=action();}
    catch(const std::invalid_argument& e){r.kind="invalid";r.message=e.what();}
    catch(const std::out_of_range& e){r.kind="range";r.message=e.what();}
    catch(const std::overflow_error& e){r.kind="overflow";r.message=e.what();}
    return r;
}
Result call(double x,double bucket,OccupancyCellCounter counter) {
    entries={};observing=true;
    const auto r=outcome([&]{return occupancy_cell_index(x,bucket,counter);});
    observing=false;
    require(entries[4]==1,"each attempted scalar call must enter exactly once");
    for(std::size_t i=0;i<entries.size();++i)if(i!=4)require(!entries[i],"unrelated scalar entry");
    return r;
}
void scalar_contract() {
    QuantizationCounts expected,direct,slotted;
    OccupancyCellSlot slot(&slotted);OccupancyCellCounter view(slot),copied_view=view;
    require(slotted.empty(),"slot construction must be lazy");
    const double inf=std::numeric_limits<double>::infinity(),nan=std::numeric_limits<double>::quiet_NaN();
    for(double x:{-0.,0.,-10.1,10.1,double(std::numeric_limits<int>::min()),
                  double(std::numeric_limits<int>::max()),1e300,inf,-inf,nan})
        for(double bucket:{-.75,.75,2.5,1.,0.,-0.,1e-300,inf,nan}) {
            const auto old=outcome([&]{return reference(x,bucket,&expected);});
            require(call(x,bucket,&direct)==old&&call(x,bucket,copied_view)==old,"scalar result or failure changed");
            require(expected==direct&&expected==slotted,"entry receipts changed");
        }
    for(int i=0;i<100;++i) {
        const auto key="unrelated_"+std::to_string(i);
        expected[key]=i;direct[key]=i;slotted[key]=i;
    }
    (void)reference(1,2,&expected);(void)occupancy_cell_index(1,2,&direct);
    (void)occupancy_cell_index(1,2,&slotted);
    require(call(1,2,&direct)==call(1,2,view),"view disagrees after insertions/direct call");
    (void)reference(1,2,&expected);
    require(expected==direct&&expected==slotted,"binding retained stale count value");
    OccupancyCellSlot disabled(nullptr);
    require(call(1.25,.5,disabled)==call(1.25,.5,nullptr),"null binding changed result");
    require(occupancy_cell_index(1.25,.5)==2,"default registry-style invocation changed");
    for(bool prebound:{false,true}) {
        const auto max=std::numeric_limits<std::size_t>::max();
        QuantizationCounts a{{names[4],max-1},{"prefix",17}},b=a;
        OccupancyCellSlot binding(&b);
        if(prebound) {
            const auto old=outcome([&]{return reference(1,1,&a);});
            require(call(1,1,binding)==old,"MAX-1 handling changed");
        } else {a[names[4]]=max;b[names[4]]=max;}
        const auto saved=b;
        const auto old=outcome([&]{return reference(nan,0,&a);});
        const auto got=call(nan,0,binding);
        require(got==old&&got.kind=="overflow"&&a==b&&b==saved,"overflow must precede input validation without increment");
    }
}
template<class F> void measured(QuantizationCounts& counts,F action) {
    auto expected=counts;entries={};observing=true;
    try{action();}catch(...){observing=false;throw;}
    observing=false;
    for(std::size_t i=0;i<entries.size();++i)if(entries[i])checked_quantization_add(expected,names[i],entries[i]);
    require(counts==expected,"producer receipts differ from independent actual function entries");
}
void map_lifetimes() {
    QuantizationCounts counts;
    auto run=[&](QuantizationCounts& c){OccupancyCellSlot binding(&c);(void)occupancy_cell_index(3,2,binding);};
    run(counts);counts.clear();run(counts);
    require(counts==QuantizationCounts{{names[4],1}},"clear reused stale binding");
    auto copy=counts;run(copy);run(counts);
    require(copy==counts,"copy inherited another invocation's binding");
    QuantizationCounts other{{names[4],19}};counts.swap(other);run(counts);run(other);
    require(counts.at(names[4])==20&&other.at(names[4])==3,"swap retained stale binding");
    counts={{names[4],7}};run(counts);
    checked_quantization_merge(counts,QuantizationCounts{{names[4],11}});run(counts);
    require(counts.at(names[4])==20,"assignment/merge retained stale binding");
    std::optional<QuantizationCounts> reused;
    for(int i=0;i<4;++i){reused.emplace();run(*reused);require(reused->at(names[4])==1,"same-address reconstruction retained binding");reused.reset();}
}
void geometry() {
    Occupancy o(12,10,.1,3,2,.5,.05);
    const std::vector<Comp> comps{{-1,.25,.5,.75,2},{2,-.25,.5,.5,3}};
    QuantizationCounts counts{{"seed",23}};
    measured(counts,[&]{o.add(4,3,2,2,{.2,.3,.4,.1},{},1,comps,&counts);});
    for(int pass=0;pass<3;++pass) {
        measured(counts,[&]{
            for(int y=-1;y<11;++y)for(int x=-1;x<13;++x)
                require(o.fits_hashed(x+.125,y-.125,1,1,{},{},1,comps,&counts)==
                        o.fits_exhaustive(x+.125,y-.125,1,1,{},{},1,comps),"hashed geometry changed");
            (void)o.place_near(6,5,2,1,{},{},1,comps,-1,13,-1,11,&counts);
        });
        // Every query-local binding is gone before these ownership changes.
        auto copy=o;auto other=counts;counts.swap(other);counts.clear();
        measured(counts,[&]{copy.remove(4,3,2,2,{.2,.3,.4,.1},{},1,comps,&counts);});
        require(copy.rect_count()==0&&o.rect_count()==3,"occupancy copy/remove changed original");
    }
    QuantizationCounts none;
    measured(none,[&]{require(!o.fits_hashed(-10,0,1,1,{},{},1,{},&none),"outside query accepted");
        o.remove(100,100,1,1,{},{},1,{},&none);});
    require(none.empty(),"early return eagerly inserted cell counter");
    measured(none,[&]{require(!o.place_near(2,2,1,1,{},{},1,{},20,21,20,21,&none),"empty window accepted");});
    require(none==QuantizationCounts{{names[5],2}},"empty frontier created cell receipt");
    for(std::size_t allowed=0;allowed<4;++allowed) {
        const auto max=std::numeric_limits<std::size_t>::max();
        QuantizationCounts c{{names[4],max-allowed},{"seed",7}};
        entries={};observing=true;
        const auto failure=outcome([&]{return o.fits_hashed(1,1,1,1,{},{},1,{},&c);});
        observing=false;
        require(failure.kind=="overflow"&&entries[4]==allowed+1&&c.at(names[4])==max&&c.at("seed")==7,
                "query overflow failed-prefix or entry count changed");
    }
    QuantizationCounts bad;entries={};observing=true;
    const auto failure=outcome([&]{return o.fits_hashed(1,std::numeric_limits<double>::quiet_NaN(),1,1,{},{},1,{},&bad);});
    observing=false;
    require(failure.kind=="invalid"&&entries[4]==1&&bad==QuantizationCounts{{names[4],1}},"invalid query prefix changed");
}
void threads() {
    const Occupancy o(12,10,.1,3,2,.5,.05);
    std::array<QuantizationCounts,4> counts;
    std::array<std::size_t,4> observed{};
    std::array<std::thread,4> workers;
    std::atomic<int> ready{0};
    for(std::size_t i=0;i<workers.size();++i)workers[i]=std::thread([&,i]{
        ++ready;while(ready.load()!=4)std::this_thread::yield();
        entries={};observing=true;
        for(int j=0;j<100;++j)(void)o.fits_hashed(1,1,1,1,{},{},1,{},&counts[i]);
        observing=false;observed[i]=entries[4];
    });
    for(auto& worker:workers)worker.join();
    for(std::size_t i=0;i<workers.size();++i)
        require(observed[i]==400&&counts[i]==QuantizationCounts{{names[4],400}},"query binding escaped thread/invocation");
}
void boundary_frontier() {
    Occupancy blocked(6,6,1,2,1,1,.05);blocked.add(0,0,6,6,{},{},1,{});
    QuantizationCounts counts;
    measured(counts,[&]{require(!blocked.place_near(3,3,2,2,{},{},1,{},-1,7,-1,7,&counts),"blocked lattice unexpectedly fits");});
    require(counts.at(names[2])==9,"only x/y 1..3 can satisfy the body boundary, so exactly nine frontier calls");
    require(counts.at(names[4])==4,"one blocking body should need one spatial lookup, not nine");
    QuantizationCounts oversized;
    measured(oversized,[&]{require(!blocked.place_near(3,3,5,2,{},{},1,{},-1,7,-1,7,&oversized),"oversized body unexpectedly fits");});
    require(oversized==QuantizationCounts{{names[5],2}},"impossible body creates no frontier or collision-index work");
    for(double step:{.5,1.,1.25})for(double clear:{0.,.3,1.})
    for(double w:{1.,2.4,6.})for(double h:{.5,2.,7.})for(int mask:{1,2})for(double ax:{-1.,3.1,9.}) {
        Occupancy scene(6,7,clear,2,2,step,.05);
        scene.add(2,2,1.5,2,{.2,.3,.4,.1},{},1,{{-.4,.3,.5,.7,3}});
        const std::vector<Comp> children{{-.25,.5,.5,.5,2}};
        std::optional<std::tuple<double,double,double>> best;
        // Independent full Cartesian enumeration, including boundary failures;
        // compare rounded-distance/x/y rank using exhaustive, non-hashed fits.
        for(int ix=0;ix<=static_cast<int>(6/step);++ix)for(int iy=0;iy<=static_cast<int>(7/step);++iy) {
            const double x=ix*step,y=iy*step;
            if(x>5.5||y<.25||y>6.5||!scene.fits_exhaustive(x,y,w,h,{},{},mask,children))continue;
            const auto rank=std::make_tuple(occupancy_frontier_key1dp(std::abs(x+w/2-ax)+std::abs(y+h/2-2.65)),x,y);
            if(!best||rank<*best)best=rank;
        }
        const auto actual=scene.place_near(ax,2.65,w,h,{},{},mask,children,-.5,5.5,.25,6.5);
        require(bool(actual)==bool(best),"axis pruning changed feasibility versus exhaustive lattice");
        if(best&&!(actual->x==std::get<1>(*best)&&actual->y==std::get<2>(*best))) {
            std::cerr<<"oracle witness step="<<step<<" clear="<<clear<<" wh="<<w<<","<<h<<" mask="<<mask<<" ax="<<ax<<" actual="<<actual->x<<","<<actual->y<<" expected="<<std::get<1>(*best)<<","<<std::get<2>(*best)<<'\n';
            require(false,"axis pruning changed the best rounded-distance/x/y pose");
        }
    }
}
void alternative_poses() {
    for(double step:{.5,1.})for(int mask:{1,2,3})for(double ax:{-1.,3.05,7.}) {
        Occupancy scene(7,6,.1,2,2,step,.05);
        const std::vector<Comp> children{{-.25,.5,.5,.5,2}};
        scene.add(3,2,1,2,{.1,.2,.3,.1},{},1,{{.25,-.5,.5,.5,3}});
        std::vector<std::tuple<double,double,double>> oracle;
        for(int ix=0;ix<=static_cast<int>(7/step);++ix)for(int iy=0;iy<=static_cast<int>(6/step);++iy) {
            const double x=ix*step,y=iy*step;
            if(x<.5||x>6||y<.5||y>5||!scene.fits_exhaustive(x,y,1,1,{},{},mask,children))continue;
            oracle.emplace_back(occupancy_frontier_key1dp(std::abs(x+.5-ax)+std::abs(y+.5-2.65)),x,y);
        }
        std::sort(oracle.begin(),oracle.end());
        QuantizationCounts legacy_counts,one_counts;
        const auto first=scene.place_near(ax,2.65,1,1,{},{},mask,children,.5,6,.5,5,&legacy_counts);
        const auto one=scene.place_near_candidates(ax,2.65,1,1,{},{},mask,children,.5,6,.5,5,1,10000,&one_counts);
        require(legacy_counts==one_counts&&bool(first)==!one.poses.empty(),"single-result adapter changed receipts or feasibility");
        if(first)require(first->x==one.poses[0].x&&first->y==one.poses[0].y,"single-result adapter changed incumbent");
        for(std::size_t limit:{1u,4u,10000u})for(std::size_t budget:{1u,3u,10000u}) {
            QuantizationCounts counts;NearPoseCandidates result;
            measured(counts,[&]{result=scene.place_near_candidates(ax,2.65,1,1,{},{},mask,children,.5,6,.5,5,limit,budget,&counts);});
            require(result.frontier_nodes<=budget&&result.poses.size()<=limit,"alternative query exceeded explicit limits");
            require(result.poses.size()<=oracle.size(),"alternative query invented feasibility");
            for(std::size_t i=0;i<result.poses.size();++i)
                require(result.poses[i].x==std::get<1>(oracle[i])&&result.poses[i].y==std::get<2>(oracle[i]),"alternative list differs from exhaustive ordered prefix");
            if(result.search_complete)require(!result.budget_exhausted&&result.poses.size()==oracle.size(),"incomplete domain reported exhausted");
            if(result.budget_exhausted)require(!result.search_complete&&result.frontier_nodes==budget,"budget status lost executed frontier work");
            require(counts[names[2]]==result.frontier_nodes,"alternative frontier count differs from actual precision calls");
            if(budget==10000)require(!result.budget_exhausted&&result.poses.size()==std::min(limit,oracle.size()),"large budget lost legal alternatives");
        }
    }
    Occupancy scene(10,4,0,2,0,1,.05);
    const auto alternatives=scene.place_near_candidates(5,2,2,2,{},{},1,{},0,8,1,1,9,100);
    require(alternatives.poses.size()==9,"backtracking fixture missing alternatives");
    std::size_t rescued=0;
    for(std::size_t i=0;i<alternatives.poses.size();++i) {
        auto branch=scene;const auto& p=alternatives.poses[i];branch.add(p.x,p.y,p.w,p.h,{},{},1,{});
        const auto large=branch.place_near(3,2,6,4,{},{},1,{},0,0,0,0);
        if(!i)require(!large,"nearest-only fixture should block the constrained group");
        if(large)++rescued;
    }
    require(rescued>0&&scene.rect_count()==0,"alternative exploration failed to recover or mutated its incumbent");
    QuantizationCounts invalid;
    for(const auto limits:std::vector<std::pair<std::size_t,std::size_t>>{{0,1},{1,0}}) {
        const auto failure=outcome([&]{(void)scene.place_near_candidates(5,2,2,2,{},{},1,{},0,8,1,1,limits.first,limits.second,&invalid);return 0;});
        require(failure.kind=="invalid"&&invalid.empty(),"zero limits performed search work");
    }
    const auto empty=scene.place_near_candidates(5,2,2,2,{},{},1,{},20,21,20,21,4,1);
    require(empty.poses.empty()&&empty.search_complete&&!empty.budget_exhausted&&!empty.frontier_nodes,"empty domain misreported as budget exhaustion");
    for(double bad:{std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}) {
        const auto failure=outcome([&]{(void)scene.place_near_candidates(bad,2,2,2,{},{},1,{},20,21,20,21,4,1,&invalid);return 0;});
        require(failure.kind=="invalid"&&invalid.empty(),"invalid anchor passed as an exhausted empty domain");
    }
    auto blocked=scene;blocked.add(0,0,10,4,{},{},1,{});
    QuantizationCounts partial_counts,complete_counts;
    measured(partial_counts,[&]{
        const auto partial=blocked.place_near_candidates(5,2,2,2,{},{},1,{},0,8,1,1,4,2,&partial_counts);
        require(partial.poses.empty()&&partial.budget_exhausted&&!partial.search_complete&&partial.frontier_nodes==2,
                "bounded failure must not certify global infeasibility");
    });
    measured(complete_counts,[&]{
        const auto complete=blocked.place_near_candidates(5,2,2,2,{},{},1,{},0,8,1,1,4,100,&complete_counts);
        require(complete.poses.empty()&&!complete.budget_exhausted&&complete.search_complete&&complete.frontier_nodes==9,
                "exhaustive empty result must certify the queried lattice only");
    });
    std::cout<<"bounded alternative poses PASS (ordered oracle, exact receipts, greedy-trap recovery)\n";
}
void child_rejection_cache() {
    Occupancy blocked(6,6,1,2,1,1,.05);blocked.add(0,0,6,6,{},{},1,{});
    const std::vector<Comp> children{{0,0,2,2,1}};
    QuantizationCounts counts;
    measured(counts,[&]{require(!blocked.place_near(3,3,2,2,{},{},2,children,-1,7,-1,7,&counts),"opposite-face child obstruction missed");});
    require(counts.at(names[2])==9&&counts.at(names[4])==8,
            "child rejection must reuse its exact offset/mask after the initial body+child lookup");
    QuantizationCounts repeated;
    measured(repeated,[&]{require(!blocked.place_near(3,3,2,2,{},{},2,children,-1,7,-1,7,&repeated),"repeat lost obstruction");});
    require(repeated==counts,"rejection cache or operation sink escaped its invocation");
    auto edited=blocked;
    edited.remove(0,0,6,6,{},{},1,{});
    require(bool(edited.place_near(3,3,2,2,{},{},2,children,-1,7,-1,7)),"copied/removed geometry retained stale obstacle");
    require(bool(blocked.place_near(3,3,2,2,{},{},2,{},-1,7,-1,7)),"new child-free invocation retained stale child");
    require(!blocked.place_near(3,3,2,2,{},{},2,children,-1,7,-1,7),"copy edits changed original occupancy");
}
void changing_blockers_oracle() {
    for(int scenario=0;scenario<24;++scenario) {
        Occupancy scene(16,14,.2,2,2,.5,.05+1e-9);
        scene.add(3,2,3,4,{.3,.6,.2,.1},{.1,0,0,0},1,{{-.5,1,1,2,2}});
        scene.add(8,7,4,3,{.4,.1,.5,.2},{0,.2,0,.1},2,{{1,-1,2,1,1}});
        scene.add(2+scenario%7,5+scenario%3,2,2,{},{},3,{});
        const int mask=1+scenario%2;
        const double w=1.5+scenario%3,h=1+scenario%4;
        const double ax=2.15+scenario%11,ay=1.75+scenario%9;
        const Halo reach{.2,.3,.1,.4},inset{0,.1,0,.2};
        const std::vector<Comp> children{{-.5,.5,.75,1.25,3-mask,{.2,.4,.1,.3},{}},
                                         {w-.5,-.5,1,1,3,{},{}}};
        std::optional<std::tuple<double,double,double>> best;
        for(int ix=0;ix<=32;++ix)for(int iy=0;iy<=28;++iy) {
            const double x=ix*.5,y=iy*.5;
            if(!scene.fits_exhaustive(x,y,w,h,reach,inset,mask,children))continue;
            const auto rank=std::make_tuple(occupancy_frontier_key1dp(std::abs(x+w/2-ax)+std::abs(y+h/2-ay)),x,y);
            if(!best||rank<*best)best=rank;
        }
        QuantizationCounts counts;
        measured(counts,[&]{
            const auto hit=scene.place_near(ax,ay,w,h,reach,inset,mask,children,0,16,0,14,&counts);
            require(bool(hit)==bool(best),"cached blocker changed oracle feasibility");
            if(best)require(hit->x==std::get<1>(*best)&&hit->y==std::get<2>(*best),
                            "cached body/child blocker changed rounded-distance optimum");
        });
    }
}
}
extern "C" void __cyg_profile_func_enter(void* fn,void*) {
    if(!observing)return;
    if(fn==reinterpret_cast<void*>(&schgen::occupancy_component_precision4dp))++entries[0];
    else if(fn==reinterpret_cast<void*>(&schgen::occupancy_reach_precision4dp))++entries[1];
    else if(fn==reinterpret_cast<void*>(&schgen::occupancy_frontier_key1dp))++entries[2];
    else if(fn==reinterpret_cast<void*>(&schgen::occupancy_shape_key4dp))++entries[3];
    else if(fn==reinterpret_cast<void*>(&schgen::occupancy_cell_index))++entries[4];
    else if(fn==reinterpret_cast<void*>(&schgen::occupancy_axis_count))++entries[5];
}
extern "C" void __cyg_profile_func_exit(void*,void*){}
int main(){try{scalar_contract();map_lifetimes();geometry();threads();boundary_frontier();alternative_poses();child_rejection_cache();changing_blockers_oracle();
    std::cout<<"occupancy cell counter contracts PASS (independent function-entry proof)\n";
}catch(const std::exception& e){observing=false;std::cerr<<e.what()<<'\n';return 1;}}
