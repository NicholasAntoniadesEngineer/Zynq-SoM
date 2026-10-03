#include "schgen/occupancy.hpp"
#include "schgen/occupancy_precision.hpp"
#include <array>
#include <atomic>
#include <cmath>
#include <iostream>
#include <limits>
#include <optional>
#include <stdexcept>
#include <thread>
#include <type_traits>

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
int main(){try{scalar_contract();map_lifetimes();geometry();threads();
    std::cout<<"occupancy cell counter contracts PASS (independent function-entry proof)\n";
}catch(const std::exception& e){observing=false;std::cerr<<e.what()<<'\n';return 1;}}
