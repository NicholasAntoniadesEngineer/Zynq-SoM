#include "pack_grid_precision_fixture.hpp"
#include "floorplan_precision_fixture.hpp"
#include "connector_precision_fixture.hpp"
#include "pcb_placement_fixture.hpp"
#include "schgen/pack_grid_precision.hpp"
#include "schgen/pack.hpp"
#include "schgen/occupancy.hpp"
#include "schgen/pcb_emit.hpp"
#include "schgen/native_audit_state.hpp"
#include "schgen/board_policy.hpp"
#include "schgen/board_pipeline.hpp"
#include <atomic>
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <thread>

namespace {
using namespace schgen;
using pack_grid_precision_fixture::names;
std::array<std::atomic<std::size_t>,6> entries{};
std::atomic<bool> recording{false};
const std::array<void*,6> addresses{{reinterpret_cast<void*>(&silk_cell_floor),
    reinterpret_cast<void*>(&breathe_grid_extent), reinterpret_cast<void*>(&breathe_stamp_index),
    reinterpret_cast<void*>(&breathe_free_index), reinterpret_cast<void*>(&refdes_size_precision3dp),
    reinterpret_cast<void*>(&refdes_pose_precision4dp)}};
void demand(bool ok, const char* why) { if (!ok) throw std::runtime_error(why); }
template<class F> void rejects(F f) {
    bool caught=false; try { f(); } catch (const std::exception&) { caught=true; }
    demand(caught,"negative contract accepted");
}
void begin() { for(auto& n:entries)n=0; recording=true; }
QuantizationCounts end() {
    recording=false; QuantizationCounts q;
    for(std::size_t i=0;i<names.size();++i)if(entries[i])q[names[i]]=entries[i].load();
    return q;
}
void receipt(const QuantizationCounts& q,const QuantizationCounts& actual) {
    const auto owned=pack_grid_precision_fixture::select(q);
    if(owned!=actual) {
        std::ostringstream error;error<<"scalar entries and receipt differ; owned:";
        for(const auto& [name,n]:owned)error<<' '<<name<<'='<<n;
        error<<"; actual:";for(const auto& [name,n]:actual)error<<' '<<name<<'='<<n;
        throw std::runtime_error(error.str());
    }
}
std::uint64_t bits(double x) { std::uint64_t n;std::memcpy(&n,&x,sizeof n);return n; }
void adapters() {
    const QuantizationCounts prior{{"legalize_pose_quantum",7},{"est_via_cost",11},
        {"silk_cell_floor_typo",13},{"breathe_free_index_future",17}};
    auto mixed=prior;for(const auto& n:names)mixed[n]=19;
    demand(pack_grid_precision_fixture::select(mixed,false)==prior,"exact family filter");
    demand(pack_geometry_precision_fixture::select(mixed,false)==prior,"geometry adapter");
    demand(pack_precision_fixture::select(mixed,false)==prior,"pack adapter");
    demand(output_precision_fixture::select(mixed,false)==prior,"output adapter");
    demand(placement_precision_fixture::select(mixed,false)==prior,"placement adapter");
    demand(stage_precision_fixture::select(mixed,false)==prior,"stage adapter");
    demand(legalize_precision_fixture::select(mixed,false)==prior,"legalize adapter");
    demand(occupancy_precision_fixture::select(mixed,false)==prior,"occupancy adapter");
    demand(floorplan_precision_fixture::select(mixed,false)==prior,"floorplan adapter");
    std::ostringstream a,b;connector_fixture::counts(a,"q",prior);connector_fixture::counts(b,"q",mixed);
    demand(a.str()==b.str(),"connector adapter");
    // A misspelled or new family must not disappear with the six reviewed names.
    mixed["silk_cell_floor_new"]=1;
    demand(pack_grid_precision_fixture::select(mixed,false)!=prior,"unknown-name mutation hidden");
    rejects([&]{receipt({{names[0],2}},{{names[0],1}});});
    rejects([&]{receipt({},{{names[0],1}});});
}
void scalars() {
    for(int k=-1024;k<=1024;++k) {
        const double x=k/16.; QuantizationCounts q;begin();
        demand(silk_cell_floor(x,1,&q)==static_cast<int>(std::floor(x)),"floor oracle");
        demand(breathe_stamp_index(x,&q)==k/16,"stamp integer oracle");
        demand(breathe_free_index(x,&q)==k/16,"free integer oracle");
        receipt(q,end());
    }
    for(double x:{-1.999,-1.,-.75,-0.,0.,.999,1.,2147483645.,2147483645.75}) {
        QuantizationCounts q;begin();
        demand(breathe_grid_extent(x,1,&q)==static_cast<int>(x)+2,"extent trunc/add order");
        receipt(q,end());
    }
    for(auto op:{breathe_stamp_index,breathe_free_index})
        for(double x:{-2147483648.75,-2147483648.,2147483647.,2147483647.75}) {
            QuantizationCounts q;begin();demand(op(x,&q)==static_cast<int>(x),"edge trunc oracle");receipt(q,end());
        }
    for(int digits:{3,4})for(int k=-256;k<=256;++k) {
        const double mid=(k+.5)/(digits==3?1000.:10000.);
        for(double x:{std::nextafter(mid,-INFINITY),mid,std::nextafter(mid,INFINITY),-0.}) {
            QuantizationCounts q;begin();const double got=digits==3?
                refdes_size_precision3dp(x,&q):refdes_pose_precision4dp(x,&q);
            demand(bits(got)==bits(py_round(x,digits)),"rounding bits changed");receipt(q,end());
        }
    }
    for(double x:{std::numeric_limits<double>::max(),-std::numeric_limits<double>::max(),
                  std::numeric_limits<double>::denorm_min(),-std::numeric_limits<double>::denorm_min()}) {
        QuantizationCounts q;begin();
        demand(bits(refdes_size_precision3dp(x,&q))==bits(py_round(x,3)),"extreme size round");
        demand(bits(refdes_pose_precision4dp(x,&q))==bits(py_round(x,4)),"extreme pose round");
        receipt(q,end());
    }
    for(double x:{double(NAN),double(INFINITY),double(-INFINITY)}) {
        QuantizationCounts q;begin();
        rejects([&]{silk_cell_floor(x,1,&q);});rejects([&]{breathe_grid_extent(x,1,&q);});
        rejects([&]{breathe_stamp_index(x,&q);});rejects([&]{breathe_free_index(x,&q);});
        rejects([&]{refdes_size_precision3dp(x,&q);});rejects([&]{refdes_pose_precision4dp(x,&q);});
        auto actual=end();receipt(q,actual);demand(actual.size()==6,"throwing entries lost");
    }
    for(double x:{-2147483649.,2147483648.,1e100}) {
        QuantizationCounts q;begin();rejects([&]{silk_cell_floor(x,1,&q);});
        rejects([&]{breathe_stamp_index(x,&q);});rejects([&]{breathe_free_index(x,&q);});receipt(q,end());
    }
    for(double x:{-2.,2147483646.,1e100})rejects([&]{breathe_grid_extent(x,1);});
    for(double c:{0.,-1.,double(NAN),double(INFINITY)}) {
        rejects([&]{silk_cell_floor(1,c);});rejects([&]{breathe_grid_extent(1,c);});
    }
    QuantizationCounts full{{names[0],std::numeric_limits<std::size_t>::max()}};
    begin();rejects([&]{silk_cell_floor(0,1,&full);});
    demand(end()==QuantizationCounts{{names[0],1}}&&full.at(names[0])==std::numeric_limits<std::size_t>::max(),"overflow mutated sink");
    for(std::size_t i=1;i<names.size();++i) {
        QuantizationCounts limit{{names[i],std::numeric_limits<std::size_t>::max()}};begin();
        rejects([&]{switch(i){
        case 1:(void)breathe_grid_extent(1,1,&limit);break;
        case 2:(void)breathe_stamp_index(1,&limit);break;
        case 3:(void)breathe_free_index(1,&limit);break;
        case 4:(void)refdes_size_precision3dp(1,&limit);break;
        default:(void)refdes_pose_precision4dp(1,&limit);break;
        }});
        demand(end()==QuantizationCounts{{names[i],1}}&&limit.at(names[i])==std::numeric_limits<std::size_t>::max(),"overflow mutated sink");
    }
}
void grids() {
    QuantizationCounts q;begin();
    SilkBoxIndex index(1);index.add({-.75,-.75,.75,.75},&q);
    demand(index.pen({-.5,-.5,.5,.5},&q)==1,"silk overlap");
    auto copy=index;copy.add({4,4,5,5},&q);
    demand(!index.hits({4,4,5,5},&q)&&copy.hits({4,4,5,5},&q),"index copy/receipt isolation");
    receipt(q,end());
    q.clear();begin();BreatheGrid grid(2,2,1,0,0,&q);
    // Negative fractional stamps truncate to zero, unlike floor.
    grid.stamp({-.75,-.75,.25,.25},1,&q);
    demand(!grid.free({0,0,.25,.25},&q),"negative stamp truncation");
    grid.stamp({-.75,-.75,.25,.25},0,&q);
    auto trial=grid;trial.stamp({1,1,1,1},1,&q);
    demand(!trial.free({1,1,1,1},&q)&&grid.free({1,1,1,1},&q),"rollback altered original");
    grid=trial;grid.stamp({1,1,1,1},0,&q);
    demand(grid.free({1,1,1,1},&q),"restamp rollback");
    auto observed=end();receipt(q,observed);
    demand(q.at(names[1])==2&&q.at(names[2])==16&&q.at(names[3])==16,"explicit grid path counts");
    q.clear();begin();demand(!grid.free({-.01,0,1,1},&q),"free early bounds rejection");
    grid.stamp({-4,-4,-3,-3},1,&q);receipt(q,end());
    demand(q==QuantizationCounts{{names[2],4}},"early-rejection conversion order");
    for(const Box4 box:std::vector<Box4>{{1,0,0,1},{0,0,NAN,1},{0,0,INFINITY,1}}) {
        rejects([&]{grid.stamp(box,1);});rejects([&]{grid.free(box);});
    }
    rejects([&]{BreatheGrid bad(1,1,1,INFINITY,0);});
    rejects([&]{BreatheGrid bad(1e100,1,1,0,0);});
    q.clear();begin();SilkBoxIndex occupied(8),placed(8);
    occupied.add({-100,-100,100,100},&q);
    auto moved=place_refdes({0,0,2,2},"U1",1,{0,0,2,2},occupied,placed,
        {-100,-100,100,100},0,0,1,0,.8,.02,-1,1e-9,.5,{1,1,.78,.62},&q);
    receipt(q,end());demand(moved.moved&&q.at(names[4])>=3&&q.at(names[5])==2,"rejected shrink or pose entries lost");
    std::array<QuantizationCounts,2> sinks;std::array<std::thread,2> threads;begin();
    for(std::size_t i=0;i<threads.size();++i)threads[i]=std::thread([&,i]{
        BreatheGrid local(2,2,1,0,0,&sinks[i]);
        for(int k=0;k<20;++k){local.stamp({0,0,1,1},k%2,&sinks[i]);(void)local.free({0,0,1,1},&sinks[i]);}
    });
    for(auto& t:threads)t.join();auto observed_threads=end();
    demand(sinks[0]==sinks[1]&&sinks[0]==QuantizationCounts{{names[1],2},{names[2],80},{names[3],80}},"concurrent sink isolation");
    auto total=sinks[0];checked_quantization_merge(total,sinks[1]);receipt(total,observed_threads);
}
void registry() {
    NativeQuantizations all;register_native_quantizations(all);const auto ds=all.declarations();
    demand(ds.size()==155,"122 baseline plus9 search plus18 plain plus6 grid");
    for(std::size_t i=0;i<names.size();++i) {
        auto d=std::find_if(ds.begin(),ds.end(),[&](const auto& row){return row.name==names[i];});
        demand(d!=ds.end()&&d->arity==(i<2?2U:1U)&&
            d->symbol=="native/src/pack_grid_precision.cpp::schgen::"+names[i],"independent registry identity");
        begin();all.invoke(names[i],i<2?std::vector<double>{1.23455,1}:std::vector<double>{1.23455});
        demand(end()==QuantizationCounts{{names[i],1}},"registry did not enter actual scalar");
        const auto prior=all.engagements();begin();rejects([&]{all.invoke(names[i],{});});
        demand(end().empty()&&all.engagements()==prior,"wrong arity performed work");
    }
    for(const auto& manifest:{native_board_policy_audit_sources(),board_pipeline_audit_sources()})
        demand(std::count_if(manifest.begin(),manifest.end(),[](const auto& x){return x.path=="native/src/pack_grid_precision.cpp";})==1,"manifest source missing or duplicate");
}
void boards(const std::filesystem::path& root) {
    for(const auto* name:{"carrier","devkit_mini"}) {
        auto f=placement_fixture::load(root,name);begin();auto result=build_pcb_model(f.input);
        auto counts=pcb_placement_accounting(result);receipt(counts.quantization_engagements,end());
        demand(counts.quantization_engagements.at(names[1])>0&&counts.quantization_engagements.at(names[2])>0,"full placement has no grid receipts");
        begin();auto replay=pcb_placement_accounting(result);
        demand(end().empty()&&replay.quantization_engagements==counts.quantization_engagements,"replay created work");
        const auto policy=pcb_emit_policy(f.input.floorplan.project);QuantizationCounts external;
        begin();auto emission=render_pcb(result.model,policy,&external);receipt(external,end());
        demand(emission.quantization_engagements.empty()&&external.at(names[0])>0&&external.at(names[5])>0,"emission sink ownership");
        begin();auto repeated=render_pcb(result.model,policy);receipt(repeated.quantization_engagements,end());
        demand(repeated.pcb==emission.pcb&&repeated.diagnostics==emission.diagnostics&&
            repeated.quantization_engagements==external,"repeat full output/receipt drift");
        std::cout<<name;for(const auto& [key,n]:pack_grid_precision_fixture::select(external))std::cout<<' '<<key<<'='<<n;
        std::cout<<'\n';
    }
}
}
extern "C" void __cyg_profile_func_enter(void* fn,void*) {
    if(!recording.load(std::memory_order_relaxed))return;
    for(std::size_t i=0;i<addresses.size();++i)if(fn==addresses[i]){++entries[i];return;}
}
extern "C" void __cyg_profile_func_exit(void*,void*) {}
int main(int argc,char** argv) {try {
    demand(argc==2||argc==3,"root [--boards] required");
    adapters();scalars();grids();registry();
    if(argc==3){demand(std::string(argv[2])=="--boards","unknown mode");boards(argv[1]);}
    std::cout<<"PASS grid/silk actual-entry, scalar, negative, mutation, registry and adapter contracts\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
