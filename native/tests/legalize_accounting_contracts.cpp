#include "pcb_placement_fixture.hpp"
#include "floorplan_precision_fixture.hpp"
#include "stage_precision_fixture.hpp"
#ifndef LEGALIZE_LEGACY_PROBE
#include "buried_policy_fixture.hpp"
#endif
#include "schgen/legalize.hpp"
#include "schgen/quantize.hpp"
#ifndef LEGALIZE_LEGACY_PROBE
#include "schgen/legalize_precision.hpp"
#endif
#include <array>
#include <cstring>
#include <iostream>
#include <limits>

namespace {
using namespace schgen;
void require(bool ok,const std::string& why){if(!ok)throw std::runtime_error(why);}
bool observing=false;
std::size_t pose_entries=0;
const std::array<const char*,7> names{{"legalize_position_precision4dp","legalize_centroid_precision4dp",
    "legalize_bbox_precision4dp","legalize_anchor_precision4dp","legalize_bound_precision4dp",
    "legalize_margin_precision4dp","legalize_trial_pose_precision4dp"}};
std::array<std::size_t,7> entries{};
#ifndef LEGALIZE_LEGACY_PROBE
const std::array<double(*)(double,QuantizationCounts*),7> operations{{legalize_position_precision4dp,
    legalize_centroid_precision4dp,legalize_bbox_precision4dp,legalize_anchor_precision4dp,
    legalize_bound_precision4dp,legalize_margin_precision4dp,legalize_trial_pose_precision4dp}};
#define SINK , &counts
#else
#define SINK
#endif
bool added(const std::string& name){return std::find(names.begin(),names.end(),name)!=names.end();}
QuantizationCounts legacy(QuantizationCounts q){for(const auto* n:names)q.erase(n);return stage_precision_fixture::select(q,false);}
QuantizationCounts additions(const QuantizationCounts& q){auto a=q;for(auto i=a.begin();i!=a.end();)if(!added(i->first))i=a.erase(i);else ++i;return a;}
void begin(){entries={};pose_entries=0;observing=true;}
void end(const QuantizationCounts& q){observing=false;
#ifdef LEGALIZE_PERFORMANCE_PROBE
    (void)q;
#else
    const auto p=q.find("legalize_pose_quantum");
    require((p==q.end()?0:p->second)==pose_entries,"legacy pose counter differs from function entries");
#ifndef LEGALIZE_LEGACY_PROBE
    QuantizationCounts actual;for(std::size_t i=0;i<names.size();++i)if(entries[i])actual[names[i]]=entries[i];
    require(additions(q)==actual,"precision counts differ from independent scalar entries");
#endif
#endif
}
void print_counts(std::ostream& out,const QuantizationCounts& q){for(const auto& [n,v]:legacy(q))out<<n<<' '<<v<<'\n';}
void evals(std::ostream& out,const std::vector<EvalTermOut>& values){for(const auto& v:values)
    out<<v.measured<<' '<<v.bound<<' '<<v.margin<<' '<<v.ok<<' '<<std::quoted(v.note)<<'\n';}
#ifndef LEGALIZE_LEGACY_PROBE
std::uint64_t bits(double value){std::uint64_t word;std::memcpy(&word,&value,sizeof word);return word;}
void scalars(){
    QuantizationCounts counts;begin();
    for(const auto op:operations)for(const double x:{-0.0,0.0,.00005,-.00005,1.23455,-1.23455,
            std::nextafter(1.23455,0.),std::nextafter(1.23455,2.),1e100,
            std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity(),
            std::numeric_limits<double>::quiet_NaN()}){
        const auto expected=py_round(x,4),actual=op(x,&counts);
        require(std::isnan(expected)?std::isnan(actual):bits(actual)==bits(expected),"scalar bit semantics");
    }
    end(counts);
    const auto saved=counts;
    for(const auto op:operations)op(1.23455,nullptr);
    require(counts==saved,"null sink inherited invocation state");
    for(std::size_t i=0;i<names.size();++i){
        QuantizationCounts overflow{{names[i],std::numeric_limits<std::size_t>::max()}};const auto before=overflow;
        bool rejected=false;try{operations[i](1.23455,&overflow);}catch(const std::overflow_error&){rejected=true;}
        require(rejected&&overflow==before,"scalar overflow must preserve existing counter");
    }
    // Sequential invocations and copied geometry cannot retain an earlier sink.
    QuantizationCounts first,second;
    const std::vector<std::tuple<std::string,double,double>> offsets{{"p",1.23455,-2.34565}};
    const auto pure=predicted_centroid(1,2,3,4,offsets,nullptr);
    begin();const auto a=predicted_centroid(1,2,3,4,offsets,nullptr,&first);end(first);const auto keep=first;
    begin();const auto b=predicted_centroid(1,2,3,4,offsets,nullptr,&second);end(second);
    require(a==pure&&b==pure&&first==keep&&second==first,"explicit invocation isolation");
    require(first==QuantizationCounts{{names[0],2},{names[1],2}},"one component then centroid has separate rounds");
    QuantizationCounts skipped;const std::vector<std::string> no_refs;
    begin();require(!predicted_centroid(1,2,3,4,offsets,&no_refs,&skipped),"empty filter");end(skipped);
    require(skipped.empty(),"filtered coordinates fabricate work");
    QuantizationCounts failed;bool rejected=false;begin();
    try{predicted_bbox(1,2,3,4,offsets,{{"p",0,0,1,1},{"missing",0,0,1,1}},&failed);}
    catch(const std::runtime_error&){rejected=true;}end(failed);
    require(rejected&&failed==QuantizationCounts{{names[0],2}},"failure retains only executed scalar prefix");
}
#endif
void kernels(std::ostream& out){
    QuantizationCounts counts;begin();
    const std::vector<std::tuple<std::string,double,double>> offsets{{"p",.00005,-.00005},{"q",1.23455,-2.34565}};
    for(const auto& refs:std::vector<std::vector<std::string>>{{"p"},{"q"},{"missing"},{"p","q"}}){
        const auto c=predicted_centroid(.00005,-.00005,1.23455,-2.34565,offsets,&refs SINK);
        out<<bool(c)<<' ';if(c)out<<c->first<<' '<<c->second;out<<'\n';
    }
    const std::vector<std::tuple<std::string,double,double,double,double>> pads{{"p",-.01,-.01,.02,.02},{"q",1.,-3.,2.,-2.}};
    const auto box=predicted_bbox(.00005,-.00005,1.23455,-2.34565,offsets,pads SINK);
    out<<box->x0<<' '<<box->y0<<' '<<box->x1<<' '<<box->y1<<'\n';
    require(!predicted_bbox(0,0,0,0,{},{} SINK),"empty hull");
    require(!predicted_centroid(0,0,0,0,{},nullptr SINK),"empty centroid");
    // Prefix rounding survives a later missing pad; the failure has no replay.
    bool rejected=false;auto broken=pads;broken.push_back({"missing",0,0,1,1});
    try{predicted_bbox(0,0,0,0,offsets,broken SINK);}catch(const std::runtime_error&){rejected=true;}
    require(rejected,"missing pad offset must reject");
    std::vector<EvalTermIn> terms;
    for(const auto& kind:{"flow_hop","near_max","near_intent","far_min","facing"})
        for(const auto& target:{"b","@som","som_j1","missing"})terms.push_back({kind,"a",target,5.12345,true,{"q"}});
    terms.push_back({"facing","a","b",0,false,{"missing"}});
    for(bool guarded:{false,true})evals(out,evaluate_terms(100,100,Box4{1.23455,2.34565,20,30},
        {{"a",{1.23455,2.34565}},{"b",{4.56785,7.89015}}},{{"a",offsets,pads},{"b",offsets,pads}},terms,
        guarded?std::vector<std::pair<std::string,double>>{{"a",2.5}}:std::vector<std::pair<std::string,double>>{},
        {{"som_j1",{1.23455,2.34565,20,30}}},25,25 SINK));
    end(counts);print_counts(out,counts);
}
void compose(std::ostream& out,const std::filesystem::path& root){
    using namespace placement_fixture;
    const auto fixture=parse_json_file((root/"native/tests/data/floorplan/compose.json").string());
    for(const auto& row:fixture.array_value){
        FloorplanLegalizeInput in;in.board_w=number(row,"width");in.board_h=100;in.som_core_page={65,65,85,85};
        in.compact=field(row,"compact").bool_value;
        for(const auto& n:{"a","b"})in.metrics[n]={{{"p",5,5}},{{"p",0,0,10,10}},{10,10}};
        if(const auto* jack=object_field(row,"jack");jack&&jack->bool_value)in.som_j_rects["som_j1"]={40,5,50,15};
        if(field(row,"block").bool_value)in.fixed_rects.push_back({"obstacle",{0,0,100,100}});
        in.channel_demand[{"a","b"}]=static_cast<int>(number(row,"demand"));
        for(const auto& t:field(row,"terms").array_value){FloorplanTerm term;
            term.kind=t.array_value[0].string_value;term.subject="a";term.sheet="a";term.target_raw=t.array_value[1].string_value;
            term.enforced=true;term.out_refs={"p"};if(t.array_value[2].kind!=JsonKind::Null)term.bound=t.array_value[2].number_value;
            in.index.hard.push_back(term);
        }
        std::vector<FloorplanLegalizeVar> vars{{"a",10,10,{5,5},5,5},{"b",10,10,{60,5},60,5}};
        std::vector<std::string> log;QuantizationCounts counts;begin();
        const auto ok=floorplan_legalize_compact_accounted(in,vars,log,counts);end(counts);
        require(ok==field(row,"ok").bool_value,"compose feasibility");require(log==strings(field(row,"log")),"compose decision log");
        out<<string(row,"name")<<' '<<ok<<'\n';for(const auto& v:vars)out<<v.name<<' '<<v.x<<' '<<v.y<<'\n';
        for(const auto& line:log)out<<line<<'\n';print_counts(out,counts);
#ifndef LEGALIZE_LEGACY_PROBE
        if(string(row,"name")=="compaction_reverts")require(counts.at(names[6])==12&&counts.at(names[0])>0,"reverted trial precision retained");
        if(string(row,"name")=="far_reject")require(counts.at(names[6])==4&&counts.at(names[5])==1,"rejected trial precision retained");
#endif
    }
}
void boards(std::ostream& out,const std::filesystem::path& root){
#ifndef LEGALIZE_LEGACY_PROBE
    // Captured from independently instrumented scalar entries, then checked
    // against producer receipts and the immutable pre-extraction output.
    const std::array<std::array<std::size_t,7>,4> expected{{
        {{26880,640,1024,0,64,192,488}},{{91664,3400,2992,408,408,1224,1694}},
        {{26880,640,1024,0,64,192,488}},{{5040,120,192,0,12,36,72}}}};
#endif
    for(int v=0;v<4;++v){auto fixture=placement_fixture::load(root,v==1?"carrier":"devkit_mini");fixture.input.two_side=v!=2;
        if(v==3){if(!fixture.input.floorplan.spec)fixture.input.floorplan.spec=FloorplanSpec{};fixture.input.floorplan.spec->outline=std::make_pair(100.,100.);}
        begin();auto result=build_pcb_model(fixture.input);const auto total=pcb_placement_accounting(result);end(total.quantization_engagements);
#ifndef LEGALIZE_LEGACY_PROBE
        QuantizationCounts pinned;for(std::size_t i=0;i<names.size();++i)if(expected[v][i])pinned[names[i]]=expected[v][i];
        require(additions(total.quantization_engagements)==pinned,"independent additive board count fixture changed");
#endif
        require(additions(total.quantization_engagements)==additions(result.floorplan.plan.accounting.quantization_engagements),"floorplan owns new work exactly once");
        require(additions(result.zone_accounting.quantization_engagements).empty()&&additions(result.placement_accounting.quantization_engagements).empty(),"no duplicated downstream work");
        auto prior_plan=result.floorplan.plan;auto prior_total=total.quantization_engagements;
#ifndef LEGALIZE_LEGACY_PROBE
        // Validate all seven exact additions before projecting immutable old bytes.
        prior_plan=buried_policy_fixture::prior_accounted_plan(std::move(prior_plan));
        prior_total=buried_policy_fixture::prior_display_counts(std::move(prior_total));
#endif
        out<<"BOARD "<<v<<'\n';prior_plan.accounting.quantization_engagements=legacy(prior_plan.accounting.quantization_engagements);
        floorplan_precision_fixture::node(out,floorplan_plan_json(prior_plan));
        out<<render_floorplan_ledger(prior_plan);floorplan_precision_fixture::node(out,export_floorplan_spec(prior_plan));
        print_counts(out,prior_total);print_counts(out,result.zone_accounting.quantization_engagements);print_counts(out,result.placement_accounting.quantization_engagements);
        std::cerr<<"board "<<v<<" additive";for(const auto& [n,k]:additions(total.quantization_engagements))std::cerr<<' '<<n<<'='<<k;std::cerr<<'\n';
        begin();const auto a=render_floorplan_ledger(result.floorplan.plan),b=render_floorplan_ledger(result.floorplan.plan);end({});require(a==b,"cached rendering changed");
    }
}
}
extern "C" void __cyg_profile_func_enter(void* fn,void*){if(!observing)return;
    if(fn==reinterpret_cast<void*>(&schgen::legalize_pose_quantum))++pose_entries;
#ifndef LEGALIZE_LEGACY_PROBE
    for(std::size_t i=0;i<operations.size();++i)if(fn==reinterpret_cast<void*>(operations[i]))++entries[i];
#endif
}
extern "C" void __cyg_profile_func_exit(void*,void*){}
int main(int argc,char** argv){try{
    require(argc==2||argc==3,"repo [baseline]");std::ostringstream out;out<<std::hexfloat;
#ifndef LEGALIZE_LEGACY_PROBE
    scalars();
#endif
    kernels(out);compose(out,argv[1]);
    if(argc==3&&std::string(argv[2])=="--kernels-only"){
        const auto baseline=placement_fixture::read(std::filesystem::path(argv[1])/"native/tests/data/legalize_accounting/legacy_output.txt");
        require(out.str()==baseline.substr(0,baseline.find("BOARD 0\n")),"pre-change kernel/compose output drift");
        std::cerr<<"legalize accounting kernel/compose contracts PASS\n";return 0;
    }
    boards(out,argv[1]);
    if(argc==3)require(out.str()==placement_fixture::read(argv[2]),"pre-change geometry/decisions/legacy counts drift");
    else {
#ifdef LEGALIZE_LEGACY_PROBE
        std::cout<<out.str();
#else
        require(out.str()==placement_fixture::read(std::filesystem::path(argv[1])/"native/tests/data/legalize_accounting/legacy_output.txt"),"immutable pre-change geometry/decisions/legacy counts drift");
#endif
    }
    std::cerr<<"legalize accounting contracts PASS\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
