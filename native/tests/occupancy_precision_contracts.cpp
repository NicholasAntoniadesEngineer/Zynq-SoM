#include "schgen/occupancy.hpp"
#include "schgen/pack_refine.hpp"
#include "pcb_placement_fixture.hpp"
#include "occupancy_precision_fixture.hpp"
#include "schgen/native_audit_state.hpp"
#ifndef OCCUPANCY_LEGACY_PROBE
#include "schgen/occupancy_precision.hpp"
#endif
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {
using namespace schgen;
std::size_t checks=0;
void require(bool value,const char* why){++checks;if(!value)throw std::runtime_error(why);}
std::uint64_t bits(double value){std::uint64_t out;std::memcpy(&out,&value,sizeof out);return out;}
struct Digest {
    std::uint64_t value=14695981039346656037ULL;
    void word(std::uint64_t n){for(int i=0;i<8;++i){value^=n&255;value*=1099511628211ULL;n>>=8;}}
    void scalar(double n){word(bits(n));}
    void pose(const std::optional<Pose>& p){word(p.has_value());if(p){scalar(p->x);scalar(p->y);scalar(p->w);scalar(p->h);}}
};
#ifdef OCCUPANCY_LEGACY_PROBE
#define OCC_COUNTS
#else
#define OCC_COUNTS , counts
#endif
// The same unchanged scenario is compiled against pre-migration sources as a
// separate private executable. Its output pins result bits and decision order.
std::uint64_t geometry(QuantizationCounts* counts=nullptr){
    (void)counts;Digest d;
    for(const double bucket:{0.75,2.5,7.0})for(const double step:{0.5,1.0,1.25}){
        Occupancy o(12,10,.1,bucket,1,step,.05);
        const std::vector<Comp> comps{{-1.00005,.33335,.5,.75,2},{2.00005,-.25005,.5,.5,2}};
        o.add(4,3,2,2,{.2,.3,.4,.1},{},1,comps OCC_COUNTS);
        for(int y=-1;y<=10;++y)for(int x=-1;x<=12;++x){
            const bool hashed=o.fits_hashed(x+.00005,y-.00005,1,1,{},{},1,comps OCC_COUNTS);
            const bool exhaustive=o.fits_exhaustive(x+.00005,y-.00005,1,1,{},{},1,comps);
            require(hashed==exhaustive,"hash and exhaustive geometry drift");d.word(hashed);
        }
        for(const double anchor:{-1.0,4.25,10.0})
            d.pose(o.place_near(anchor,anchor,2,1,{},{},1,comps,-1,12,-1,10 OCC_COUNTS));
        auto copy=o;
        copy.remove(4,3,2,2,{.2,.3,.4,.1},{},1,comps OCC_COUNTS);
        d.word(o.rect_count());d.word(copy.rect_count());
        d.pose(copy.place_near(5,5,2,1,{},{},1,{},0,12,0,10 OCC_COUNTS));
        const auto rows=pairs_entity(4,3,2,2,{},{},1,comps OCC_COUNTS);
        for(const auto& r:rows){d.scalar(r.x);d.scalar(r.y);d.scalar(r.w);d.scalar(r.h);d.word(r.mask);}
        const std::vector<PairsBlock> blocks{{4,3,2,2,{},{},1,comps}};
        d.word(pairs_hold_from_layout(blocks,{},0,0,1,1,1,{},12,10,.25,1,.1 OCC_COUNTS));
        std::vector<SeatShapeCand> shapes;
        for(int i=0;i<4;++i){SeatShapeCand c;c.index=i;c.w=1+i*.25;c.h=1;c.mask=1;
            c.side=i%2?"bottom":"top";c.win_x1=12;c.win_y1=10;shapes.push_back(c);}
        const auto hits=seat_shape_sides(o,5,5,shapes,12,10,.1 OCC_COUNTS);
        d.word(hits.size());for(const auto& hit:hits){d.word(hit.index);d.scalar(hit.x);d.scalar(hit.y);d.scalar(hit.w);d.scalar(hit.h);d.scalar(hit.dist_key);}
        RefineBlock block;block.name="unit";block.x=4;block.y=3;block.w=2;block.h=2;
        block.reach={.2,.3,.4,.1};block.mask=1;block.comps=comps;
        block.anchor.zone_ax=7;block.anchor.zone_ay=7;block.anchor.zone_w=1;
        const auto refined=refine_pack_passes(o,{block},{},3,12,10 OCC_COUNTS);
        d.word(refined.passes);for(const auto& p:refined.poses){d.scalar(p.first);d.scalar(p.second);}
    }
    return d.value;
}
#undef OCC_COUNTS
#ifndef OCCUPANCY_LEGACY_PROBE
// Only occupancy_precision.cpp is compiled with function instrumentation.
// Test-only independent observations; production has no globals or callbacks.
bool observing=false;
std::uint64_t entries[6]{};
const char* names[6]={"occupancy_component_precision4dp","occupancy_reach_precision4dp",
    "occupancy_frontier_key1dp","occupancy_shape_key4dp","occupancy_cell_index","occupancy_axis_count"};
template<class F> QuantizationCounts measured(QuantizationCounts& counts,F action){
    const auto before=counts;for(auto& n:entries)n=0;observing=true;
    try{action();}catch(...){observing=false;throw;}
    observing=false;QuantizationCounts expected=before,delta;
    for(int i=0;i<6;++i)if(entries[i]){delta[names[i]]=entries[i];checked_quantization_add(expected,names[i],entries[i]);}
    require(counts==expected,"exported counter delta differs from independent function entries");return delta;
}
template<class F> void rejects(F action){bool failed=false;try{action();}catch(const std::exception&){failed=true;}require(failed,"invalid scalar accepted");}
void scalars(){
    QuantizationCounts counts;
    measured(counts,[&]{for(double x:{-0.0,0.0,11.24955,-11.24955,.00005,-.00005,1.25,1.35}){
        require(bits(occupancy_component_precision4dp(x,&counts))==bits(py_round(x,4)),"component bits");
        require(bits(occupancy_reach_precision4dp(x,&counts))==bits(py_round(x,4)),"reach bits");
        require(bits(occupancy_frontier_key1dp(x,&counts))==bits(py_round(x,1)),"frontier bits");
        require(bits(occupancy_shape_key4dp(x,&counts))==bits(py_round(x,4)),"shape bits");
    }
    for(double divisor:{-.75,.75,2.5})for(double x:{-10.1,-1.0,-0.0,0.0,.75,10.1}){
        require(occupancy_cell_index(x,divisor,&counts)==static_cast<int>(std::floor(x/divisor)),"cell result");
        require(occupancy_axis_count(x,divisor,&counts)==static_cast<int>(x/divisor)+1,"axis result");
    }
    require(occupancy_cell_index(std::numeric_limits<int>::min(),1,&counts)==std::numeric_limits<int>::min(),"cell minimum");
    require(occupancy_cell_index(std::numeric_limits<int>::max(),1,&counts)==std::numeric_limits<int>::max(),"cell maximum");
    require(occupancy_axis_count(std::numeric_limits<int>::max()-1.0,1,&counts)==std::numeric_limits<int>::max(),"axis maximum");
    for(double bad:{std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()}){
        rejects([&]{occupancy_cell_index(bad,1,&counts);});rejects([&]{occupancy_axis_count(bad,1,&counts);});
    }
    rejects([&]{occupancy_cell_index(1,0,&counts);});rejects([&]{occupancy_axis_count(1,0,&counts);});
    rejects([&]{occupancy_cell_index(1e30,1,&counts);});
    rejects([&]{occupancy_axis_count(std::numeric_limits<int>::max(),1,&counts);});
    });
    counts[names[0]]=std::numeric_limits<std::size_t>::max();const auto before=counts;
    rejects([&]{occupancy_component_precision4dp(1,&counts);});require(counts==before,"overflow changed counter");
    QuantizationCounts reach;observing=true;for(auto& n:entries)n=0;
    const auto actual=spatial_bounds_accounted(1,1,.1,.2,.3,2,&reach);observing=false;
    require(actual==spatial_bounds(1,1,.1,.2,.3,2),"spatial bounds changed");
    require(entries[1]==1&&reach==QuantizationCounts{{"quant_credit",1},{names[1],1}},"reach must preserve original quant_credit separately");
}
void ownership_and_rejections(){
    Occupancy invalid(6,6,0,1,0,1,.05);
    rejects([&]{invalid.add(1e100,0,1,1,{},{},1,{});});
    require(invalid.rect_count()==0,"failed coordinate conversion inserted rectangle");
    const double maximum=std::numeric_limits<int>::max();
    Occupancy extreme(maximum+2,maximum+2,0,1,0,1,.05);
    extreme.add(maximum,maximum,.5,.5,{},{},1,{});
    require(!extreme.fits_hashed(maximum,maximum,.5,.5,{},{},1,{}),"extreme cell lost collision");
    extreme.remove(maximum,maximum,.5,.5,{},{},1,{});
    require(extreme.rect_count()==0&&extreme.fits_hashed(maximum,maximum,.5,.5,{},{},1,{}),"extreme cell removal failed");
    Occupancy o(6,6,0,2,1,1,.05);QuantizationCounts first,second;
    measured(first,[&]{o.add(2,2,2,2,{},{},1,{},&first);});
    require(first==QuantizationCounts{{names[4],4}},"one rectangle executes four index calls");
    const auto saved=first;auto copy=o;
    const auto miss=measured(second,[&]{require(!copy.fits_hashed(2,2,1,1,{},{},1,{},&second),"collision expected");});
    require(miss==QuantizationCounts{{names[4],4}}&&first==saved,"rejected copied query ownership");
    measured(second,[&]{require(!copy.fits_hashed(-1,0,1,1,{},{},1,{},&second),"boundary rejection expected");});
    auto blocked=Occupancy(6,6,0,2,1,1,.05);blocked.add(0,0,6,6,{},{},1,{});
    const auto failure=measured(second,[&]{require(!blocked.place_near(3,3,1,1,{},{},1,{},0,6,0,6,&second),"fully blocked search accepted");});
    require(failure.at(names[5])==2&&failure.at(names[2])>1&&failure.at(names[4])>4,"failed search work lost");
    Occupancy empty(6,6,0,2,1,1,.05);SeatShapeCand cand;cand.w=1;cand.h=1;cand.mask=1;cand.side="top";cand.win_x1=6;cand.win_y1=6;
    auto loser=cand;loser.index=9;auto oversized=cand;oversized.w=7;
    const auto ranking=measured(second,[&]{const auto hits=seat_shape_sides(empty,3,3,{cand,loser,oversized},6,6,0,&second);
        require(hits.size()==1&&hits.front().index==0,"shape tie order changed");});
    require(ranking.at(names[3])==2&&ranking.at(names[5])==4,"losing candidate lost or skipped candidate invented work");
    const auto before=second;copy.remove(2,2,2,2,{},{},1,{});require(second==before&&first==saved,"pure copy inherited sink");
    Occupancy survivor(6,6,0,2,1,1,.05);
    {QuantizationCounts temporary;auto original=empty;original.add(1,1,1,1,{},{},1,{},&temporary);survivor=original;}
    require(survivor.fits_hashed(4,4,1,1,{},{},1,{}),"copy retained dead sink or changed geometry");
    // A failed refinement restores geometry but keeps the actual attempted work.
    RefineBlock b;b.name="blocked";b.w=7;b.h=1;b.mask=1;b.anchor.zone_w=1;b.anchor.zone_ax=3;b.anchor.zone_ay=3;
    const auto refinement=measured(second,[&]{const auto r=refine_pack_passes(blocked,{b},{},1,6,6,&second);
        require(r.passes==1&&r.poses==std::vector<std::pair<double,double>>{{0,0}},"failed refinement moved geometry");});
    require(refinement.at(names[5])==2&&refinement.at(names[2])>0,"failed refinement work lost");
}
void registry_and_boards(const std::filesystem::path& root){
    NativeQuantizations registry;register_native_quantizations(registry);
    require(registry.declarations().size()==40,"34 prior plus six occupancy operations");
    for(int i=0;i<6;++i){
        const auto declarations=registry.declarations();
        const auto d=std::find_if(declarations.begin(),declarations.end(),[&](const auto& row){return row.name==names[i];});
        require(d!=declarations.end()&&d->symbol==std::string("native/src/occupancy_precision.cpp::schgen::")+names[i]
            &&d->arity==(i<4?1u:2u),"registry binds exact operation and arity");
        const std::vector<double> args=i<4?std::vector<double>{1.23455}:std::vector<double>{3.25,1.};
        for(auto& n:entries)n=0;observing=true;const auto value=registry.invoke(names[i],args);observing=false;
        const double expected=i==4?3.:i==5?4.:py_round(args[0],i==2?1:4);
        require(bits(value)==bits(expected)&&entries[i]==1,"registry executes the actual precision function once");
        for(int j=0;j<6;++j)if(j!=i)require(entries[j]==0,"registry cannot execute another precision function");
    }
    for(int variant=0;variant<4;++variant){
        auto fixture=placement_fixture::load(root,variant==1?"carrier":"devkit_mini");
        fixture.input.two_side=variant!=2;
        if(variant==3){if(!fixture.input.floorplan.spec)fixture.input.floorplan.spec=FloorplanSpec{};fixture.input.floorplan.spec->outline=std::make_pair(100.,100.);}
        for(auto& n:entries)n=0;observing=true;
        const auto result=build_pcb_model(fixture.input);observing=false;
        QuantizationCounts expected;for(int i=0;i<6;++i)if(entries[i])expected[names[i]]=entries[i];
        const auto total=pcb_placement_accounting(result);
        require(occupancy_precision_fixture::select(result.floorplan.plan.accounting.quantization_engagements)==expected,
                "full board floorplan receipt equals independently observed entries");
        require(occupancy_precision_fixture::select(total.quantization_engagements)==expected,
                "full board aggregate imports occupancy work exactly once");
        require(occupancy_precision_fixture::select(result.zone_accounting.quantization_engagements).empty()
            &&occupancy_precision_fixture::select(result.placement_accounting.quantization_engagements).empty(),"no downstream occupancy counter duplication");
        for(const auto* name:names)require(expected.count(name)&&expected.at(name)>0,"real board invokes each occupancy precision family");
        NativeQuantizations q;NativeFallbacks f;register_native_quantizations(q);register_native_fallbacks(f);NativeAccountingInbox inbox(q,f);
        require(inbox.merge_once("pcb/placement",total)&&!inbox.merge_once("pcb/placement",total),"one receipt accepted, replay rejected");
        for(const auto* name:names)require(q.engagements().at(name)==AuditInteger::decimal(std::to_string(expected.at(name))),"exact imported occupancy engagement");
        const auto saved=total.quantization_engagements;
        for(auto& n:entries)n=0;observing=true;
        const auto a=render_floorplan_ledger(result.floorplan.plan),b=render_floorplan_ledger(result.floorplan.plan);observing=false;
        require(a==b&&pcb_placement_accounting(result).quantization_engagements==saved,"cached render preserves accounting");
        for(auto n:entries)require(n==0,"render does not re-execute occupancy operations");
    }
}
#endif
}
#ifndef OCCUPANCY_LEGACY_PROBE
extern "C" void __cyg_profile_func_enter(void* fn,void*){
    if(!observing)return;
    if(fn==reinterpret_cast<void*>(&schgen::occupancy_component_precision4dp))++entries[0];
    else if(fn==reinterpret_cast<void*>(&schgen::occupancy_reach_precision4dp))++entries[1];
    else if(fn==reinterpret_cast<void*>(&schgen::occupancy_frontier_key1dp))++entries[2];
    else if(fn==reinterpret_cast<void*>(&schgen::occupancy_shape_key4dp))++entries[3];
    else if(fn==reinterpret_cast<void*>(&schgen::occupancy_cell_index))++entries[4];
    else if(fn==reinterpret_cast<void*>(&schgen::occupancy_axis_count))++entries[5];
}
extern "C" void __cyg_profile_func_exit(void*,void*){}
#endif
int main(int argc,char** argv){try{
    if(argc>2)throw std::runtime_error("usage: occupancy_precision_contracts [repo]");
    const auto pure=geometry();
    // Captured by the independent pre-extraction executable, not recomputed
    // from the candidate: /private/tmp/occupancy-agent1.5BMaTe/proof/before.digest.
    require(pure==0xfee57f87ab3a0aa5ULL,"pre-extraction geometry digest drift");
#ifndef OCCUPANCY_LEGACY_PROBE
    scalars();ownership_and_rejections();QuantizationCounts counts;
    measured(counts,[&]{require(geometry(&counts)==pure,"accounting changed geometry bits");});
    require(counts.at(names[0])>0&&counts.at(names[2])>0&&counts.at(names[3])>0&&counts.at(names[4])>0&&counts.at(names[5])>0,"live geometry path omitted precision family");
    if(argc==2)registry_and_boards(argv[1]);
    std::cerr<<checks<<" occupancy precision contracts PASS\n";
#endif
    std::cout<<std::hex<<pure<<'\n';return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
