#include "pcb_placement_fixture.hpp"
#include "floorplan_precision_fixture.hpp"
#include "placement_precision_fixture.hpp"
#include "pcb_placement_internal.hpp"
#ifndef PLACEMENT_PRECISION_BASELINE
#include "schgen/placement_precision.hpp"
#endif
#include <atomic>
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <thread>

namespace {
using namespace schgen;
using namespace placement_precision_fixture;
std::size_t checks=0;std::ostringstream legacy,additive;
bool capture_counts=false;
[[maybe_unused]] bool first=true;
[[maybe_unused]] JsonNode expected_counts;
[[maybe_unused]] std::set<std::string> exercised;
void require(bool ok,const std::string& why){++checks;if(!ok)throw std::runtime_error(why);}
template<class F> void rejects(F f){bool rejected=false;try{f();}catch(const std::exception&){rejected=true;}require(rejected,"expected rejection");}
std::uint64_t bits(double value){std::uint64_t word;std::memcpy(&word,&value,sizeof word);return word;}
std::atomic<bool> observing{false};std::array<std::atomic<std::size_t>,19> entries{};
#ifndef PLACEMENT_PRECISION_BASELINE
using Scalar=double(*)(double,QuantizationCounts*);
const std::array<Scalar,18> operations{{placement_turn_dimension_precision4dp,
    placement_turn_offset_precision4dp,
    placement_connector_pose_precision4dp,
    placement_behind_pose_precision4dp,
    placement_pack_extent_precision4dp,
    placement_edge_mirror_pose_precision4dp,
    placement_variant_dimension_precision4dp,
    placement_member_box_precision4dp,
    placement_member_pose_precision4dp,
    placement_bottom_pose_precision4dp,
    placement_lift_extent_precision4dp,
    placement_shape_key_precision4dp,
    placement_l4_pose_precision4dp,
    placement_edge_seat_precision4dp,
    placement_foreign_pad_precision3dp,
    placement_evict_trial_precision4dp,
    placement_emission_pose_precision4dp,
    placement_fiducial_precision4dp}};
#endif
void begin(){for(auto& count:entries)count=0;observing=true;}
QuantizationCounts end(){observing=false;QuantizationCounts out;for(std::size_t i=0;i<names.size();++i)if(entries[i])out[names[i]]=entries[i];return out;}
[[maybe_unused]] void verify(const QuantizationCounts& owned,const QuantizationCounts& calls){require(select(owned)==calls,"receipt differs from independently instrumented entries");}
void account(const std::string& label,const QuantizationCounts& owned,const QuantizationCounts& calls){
#ifdef PLACEMENT_PRECISION_BASELINE
    (void)label;(void)owned;(void)calls;
#else
#ifndef PLACEMENT_PRECISION_PLAIN
    verify(owned,calls);
#else
    (void)calls;
#endif
    const auto actual=select(owned);
    for(const auto& [name,count]:actual)if(count)exercised.insert(name);
    if(!capture_counts){
        QuantizationCounts expected;
        for(const auto& [name,value]:placement_fixture::field(expected_counts,label).object_value)
            expected[name]=static_cast<std::size_t>(value.number_value);
        require(actual==expected,"frozen independently observed receipt "+label);
    }
    if(!first)additive<<",\n";first=false;
    additive<<std::quoted(label)<<":{";bool next=false;
    for(const auto& [name,count]:actual){if(next)additive<<',';next=true;additive<<std::quoted(name)<<':'<<count;}
    additive<<'}';
#endif
}
void counts(const char* label,const QuantizationCounts& q){legacy<<label<<'\n';for(const auto& [name,count]:select(q,false))legacy<<std::quoted(name)<<' '<<count<<'\n';}
QuantizationCounts delta(QuantizationCounts after,const QuantizationCounts& before){
    for(const auto& [name,count]:before){require(after.count(name)&&after.at(name)>=count,"receipt shrank");after.at(name)-=count;}
    for(auto i=after.begin();i!=after.end();)if(!i->second)i=after.erase(i);else ++i;
    return after;
}
void offsets(const FloorplanOffsets& values){legacy<<values.size()<<'\n';for(const auto& [r,p]:values)legacy<<std::quoted(r)<<' '<<bits(p.first)<<' '<<bits(p.second)<<'\n';}
void shape(const FloorplanZoneShape& s){
    legacy<<bits(s.w)<<' '<<bits(s.h)<<' '<<std::quoted(s.tag)<<' '<<std::quoted(s.side)<<'\n';
    offsets(s.top_off);offsets(s.bot_off);legacy<<s.extra_rot.size()<<'\n';
    for(const auto& [r,v]:s.extra_rot)legacy<<std::quoted(r)<<' '<<bits(v)<<'\n';
    legacy<<s.mirror.size()<<'\n';for(const auto& [r,key]:s.mirror)legacy<<std::quoted(r)<<' '<<std::quoted(key)<<'\n';
}
void packed(const PcbStageResult& p){FloorplanZoneShape s;s.w=p.w;s.h=p.h;s.top_off=p.top;s.bot_off=p.bottom;s.extra_rot=p.rotations;shape(s);counts("stage old",p.quantization_engagements);}
void kernels(){
    using namespace pcb_placement;
    PcbPlacementInput input;Context ctx(input);Geometry g;
    const auto fp=pcb_check_footprint("Test.pretty/R.kicad_mod","(footprint R (layer F.Cu) (pad 1 smd rect (at -0.5 0) (size 0.4 0.4) (layers F.Cu)) (pad 2 smd rect (at 0.5 0) (size 0.4 0.4) (layers F.Cu)))");
    ctx.pool["fp"]=fp;g.refs_by_sheet["synthetic"]={"R1","R2","R3"};
    for(const auto& r:g.refs_by_sheet["synthetic"]){g.resolvable[r]="fp";g.bbox_of[r]={-1,-1,1,1};g.side_of[r]="top";}
    g.side_of["R3"]="bottom";
    begin();
    for(const auto& outer:{"N","S","W","E"}){
        legacy<<"connector "<<outer<<'\n';packed(pack_zone(ctx,g,g.refs_by_sheet.at("synthetic"),1.2,{{"R1",90}},outer));
    }
    auto p=pack_zone(ctx,g,g.refs_by_sheet.at("synthetic"),1.);packed(p);
    for(const auto& connectors:std::vector<Rotations>{{},{{"R1",0}}}){
        auto s=member_mirror(ctx,g,"synthetic",p,connectors);legacy<<"member "<<bool(s)<<'\n';if(s)shape(*s);
    }
    auto narrow=p;narrow.w=.1;
    require(!member_mirror(ctx,g,"synthetic",narrow,{}),"out-of-bounds mirror must reject");
    std::vector<std::string> events;
    for(const auto& s:bottom_shapes(ctx,g,"synthetic",{},std::nullopt,{},events))shape(s);
    for(const auto& s:bottom_shapes(ctx,g,"synthetic",{"R1"},p,{},events))shape(s);
    require(bottom_shapes(ctx,g,"synthetic",{"R1"},p,{"R1"},events).empty(),"contract member cannot be lifted");
    for(const auto& event:events)legacy<<std::quoted(event)<<'\n';
    FloorplanZoneShape s;s.w=10.12345;s.h=5.12345;s.top_off={{"R1",{1.23455,-0.0}}};s.bot_off={{"R2",{.00005,2.34565}}};
#ifdef PLACEMENT_PRECISION_BASELINE
    shape(turned(s));
#else
    shape(turned(s,&ctx.quantization));
#endif
    const auto calls=end();account("synthetic",ctx.quantization,calls);counts("synthetic prior",ctx.quantization);
#ifndef PLACEMENT_PRECISION_BASELINE
    const auto saved=ctx.quantization;auto copy=ctx;const auto before=copy.quantization;
    begin();const auto copied_pack=pack_zone(copy,g,g.refs_by_sheet.at("synthetic"),1.);const auto copy_calls=end();
    require(ctx.quantization==saved&&copied_pack.top==p.top&&copied_pack.bottom==p.bottom&&
        bits(copied_pack.w)==bits(p.w)&&bits(copied_pack.h)==bits(p.h),"copied context retained an old sink or changed geometry");
    account("context/copy",delta(copy.quantization,before),copy_calls);
#endif
}
#ifndef PLACEMENT_PRECISION_BASELINE
void scalars(){
    for(std::size_t i=0;i<operations.size();++i){
        const int precision=i==14?3:4;const double scale=std::pow(10.,precision);
        QuantizationCounts owned;begin();
        for(int k=-512;k<=512;++k){const double tie=(k+.5)/scale;
            for(double value:{tie,std::nextafter(tie,-INFINITY),std::nextafter(tie,INFINITY)})
                require(bits(operations[i](value,&owned))==bits(py_round(value,precision)),"scalar rounding bits");}
        for(double value:{-0.,0.,double(INFINITY),double(-INFINITY),double(NAN),std::numeric_limits<double>::max(),std::numeric_limits<double>::denorm_min()})
            require(bits(operations[i](value,&owned))==bits(py_round(value,precision)),"IEEE scalar bits");
        const auto calls=end();
#ifndef PLACEMENT_PRECISION_PLAIN
        verify(owned,calls);
#else
        (void)calls;
#endif
        const auto saved=owned;operations[i](1.23455,nullptr);require(saved==owned,"null sink mutates prior receipt");
        QuantizationCounts overflow{{names[i],std::numeric_limits<std::size_t>::max()}};
        rejects([&]{operations[i](0,&overflow);});require(overflow.at(names[i])==std::numeric_limits<std::size_t>::max(),"overflow mutated receipt");
    }
    QuantizationCounts owned;begin();
    for(double v:{-2147483648.75,-2147483648.,-1.9,-0.,0.,1.9,40.,2147483647.,2147483647.75})
        require(placement_l4_distance_trunc(v,&owned)==static_cast<int>(v),"defined truncation changed");
    for(double v:{double(NAN),double(INFINITY),double(-INFINITY),-2147483649.,2147483648.})
        rejects([&]{placement_l4_distance_trunc(v,&owned);});
    const auto calls=end();
#ifndef PLACEMENT_PRECISION_PLAIN
    verify(owned,calls);
    auto bad=owned;--bad.begin()->second;rejects([&]{verify(bad,calls);});
#else
    (void)calls;
#endif
    FloorplanZoneShape s;s.w=1.23455;s.h=2.34565;s.top_off={{"x",{.00005,-0.}}};
    QuantizationCounts first_sink,second_sink;
    const auto original=pcb_placement::turned(s,&first_sink);const auto saved=first_sink;
    const auto copied=s;const auto next=pcb_placement::turned(copied,&second_sink);
    require(first_sink==saved&&first_sink==second_sink&&original.top_off==next.top_off,"pure shape copies retained a sink");
    (void)pcb_placement::turned(s);require(first_sink==saved,"default pure call wrote previous sink");
    QuantizationCounts a,b;std::thread one([&]{for(int i=0;i<100;++i)placement_turn_offset_precision4dp(i,&a);});
    std::thread two([&]{for(int i=0;i<70;++i)placement_turn_offset_precision4dp(i,&b);});one.join();two.join();
    require(a==QuantizationCounts{{names[1],100}}&&b==QuantizationCounts{{names[1],70}},"concurrent invocation sinks leaked");
}
#endif
void rejected_eviction(const PcbPlacementInput& input,const PcbZoneResult& zones,const FloorplanStage& stage){
    pcb_placement::Placer p(input,zones,stage);p.seed();
    require(!p.som_refs.empty(),"rejection probe needs real DF40 corridor");
    const auto som=*p.som_refs.begin();p.som_refs={som};
    const auto som_pose=p.pos.at(som.first);
    const auto corridor=pcb_escape_corridor_board(*p.mod(som.first),
        evict_corridor_grid(25,som_pose.first),evict_corridor_grid(25,som_pose.second),p.rot(som.first));
    const auto ref=std::find_if(p.ctx.parts.begin(),p.ctx.parts.end(),[&](const auto& part){
        return part.ref.rfind("R",0)==0&&p.geometry.resolvable.count(part.ref)&&p.pos.count(part.ref);
    });
    require(ref!=p.ctx.parts.end(),"rejection probe needs real resistor");
    const auto box=p.box(ref->ref,{0,0});
    p.pos={{som.first,som_pose},{ref->ref,{(corridor.x0+corridor.x1-box.x0-box.x1)/2,
        (corridor.y0+corridor.y1-box.y0-box.y1)/2}}};
    p.geometry.side_of[som.first]="top";p.geometry.side_of[ref->ref]="bottom";
    // Intentionally impossible search window; all actual rounded trial poses
    // reject after arithmetic, leaving the original chosen pose unchanged.
    p.width=p.height=.1;const auto saved=p.pos;const auto before=p.ctx.quantization;
    begin();p.evict();const auto calls=end(),owned=delta(p.ctx.quantization,before);
    require(p.pos==saved&&p.out.fallback_events.back()=="corridor_stray_unmovable","rejected eviction changed placement");
    account("eviction/rejected",owned,calls);counts("rejected eviction prior",owned);offsets(p.pos);
#ifndef PLACEMENT_PRECISION_BASELINE
    require(owned.at("placement_evict_trial_precision4dp")==72,"four exits times nine rejected trials times two rounded coordinates");
#endif
}
void boards(const std::filesystem::path& root){
    for(int variant=0;variant<4;++variant){
        const std::string project=variant==1?"carrier":"devkit_mini";
        const std::string label=project+(variant==2?"_single":variant==3?"_fixed":"");
        auto f=placement_fixture::load(root,project);f.input.two_side=variant!=2;
        if(variant==3){if(!f.input.floorplan.spec)f.input.floorplan.spec=FloorplanSpec{};f.input.floorplan.spec->outline=std::make_pair(100.,100.);}
        std::cerr<<"board "<<label<<'\n';
        begin();const auto zones=build_pcb_zone_geometry(f.input);const auto zone_calls=end();
        account("zones/"+label,zones.quantization_engagements,zone_calls);
        for(const auto& [sheet,shapes]:zones.geometry.shapes){legacy<<"SHAPES "<<std::quoted(sheet)<<'\n';for(const auto& s:shapes)shape(s);}
        for(const auto& [key,fp]:zones.footprints)legacy<<"FOOTPRINT "<<std::quoted(key)<<' '<<std::quoted(fp->bytes)<<'\n';
        counts("zone standalone",zones.quantization_engagements);
        begin();const auto result=build_pcb_model(f.input);const auto calls=end();const auto total=pcb_placement_accounting(result);
        account("board/"+label,total.quantization_engagements,calls);
        legacy<<"BOARD "<<label<<'\n';floorplan_precision_fixture::node(legacy,pcb_model_json(result.model));
        auto plan=result.floorplan.plan;plan.accounting.quantization_engagements=select(plan.accounting.quantization_engagements,false);
        floorplan_precision_fixture::node(legacy,floorplan_plan_json(plan));
        legacy<<render_floorplan_ledger(plan);floorplan_precision_fixture::node(legacy,export_floorplan_spec(plan));
        for(const auto& [name,rows]:result.stages){legacy<<"STAGE "<<std::quoted(name)<<'\n';for(const auto& [r,p]:rows)
            legacy<<std::quoted(r)<<' '<<bits(std::get<0>(p))<<' '<<bits(std::get<1>(p))<<' '<<bits(std::get<2>(p))<<' '<<std::quoted(std::get<3>(p))<<'\n';}
        for(const auto& event:result.fallback_events)legacy<<"FALLBACK "<<std::quoted(event)<<'\n';
        counts("floorplan",result.floorplan.plan.accounting.quantization_engagements);
        counts("zone",result.zone_accounting.quantization_engagements);
        counts("placement",result.placement_accounting.quantization_engagements);counts("total",total.quantization_engagements);
        auto expected=select(result.floorplan.plan.accounting.quantization_engagements);
        if(result.zone_accounting_ownership==PcbZoneAccountingOwnership::SeparateFromFloorplan)checked_quantization_merge(expected,select(result.zone_accounting.quantization_engagements));
        checked_quantization_merge(expected,select(result.placement_accounting.quantization_engagements));
        require(expected==select(total.quantization_engagements),"ownership merge differs");
        begin();const auto again=pcb_placement_accounting(result);const auto text=render_floorplan_ledger(result.floorplan.plan);
        require(end().empty()&&again.quantization_engagements==total.quantization_engagements&&text==render_floorplan_ledger(result.floorplan.plan),"receipt/render replay manufactured work");
        if(variant==0)rejected_eviction(f.input,zones,result.floorplan);
    }
}
}
extern "C" void __cyg_profile_func_enter(void* fn,void*){
#ifndef PLACEMENT_PRECISION_BASELINE
    if(!observing.load())return;
    for(std::size_t i=0;i<operations.size();++i)if(fn==reinterpret_cast<void*>(operations[i])){++entries[i];return;}
    if(fn==reinterpret_cast<void*>(&schgen::placement_l4_distance_trunc))++entries[18];
#else
    (void)fn;
#endif
}
extern "C" void __cyg_profile_func_exit(void*,void*){}
int main(int argc,char** argv){try{
    require(argc==2||argc==3,"repo [--capture-legacy|--capture-counts]");
    const auto root=std::filesystem::path(argv[1]),data=root/"native/tests/data/placement_precision";
    const std::string mode=argc==3?argv[2]:"";capture_counts=mode=="--capture-counts";
    require(mode.empty()||mode=="--capture-legacy"||mode=="--capture-counts","unknown capture mode");
#ifndef PLACEMENT_PRECISION_BASELINE
    if(!capture_counts)expected_counts=parse_json_file((data/"additive_counts.json").string());
    scalars();
#endif
    kernels();boards(root);
#ifndef PLACEMENT_PRECISION_BASELINE
    for(const auto& name:names)require(exercised.count(name)!=0,"no actual consumer exercised "+name);
#endif
    if(mode=="--capture-legacy")std::cout<<legacy.str();
    else require(legacy.str()==placement_fixture::read(data/"legacy_output.txt"),"pre-migration full geometry/output/old-count bytes drift");
    if(capture_counts)std::cout<<"{\n"<<additive.str()<<"\n}\n";
    std::cerr<<checks<<" placement precision checks PASS\n";return 0;
}catch(const std::exception& e){std::cerr<<"placement precision FAILED: "<<e.what()<<'\n';return 1;}}
