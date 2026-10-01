#include "pcb_placement_fixture.hpp"
#include "ledger_accounting_fixture.hpp"
#include "floorplan_precision_fixture.hpp"
#include "output_precision_fixture.hpp"
#include "schgen/pcb_emit.hpp"
#include "schgen/pcb_escape.hpp"
#include "schgen/ratsnest_gate.hpp"
#include "schgen/occupancy.hpp"
#ifndef OUTPUT_PRECISION_LEGACY
#include "schgen/output_precision.hpp"
#endif
#include <array>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>

// Compile this same probe against the untouched base snapshot with LEGACY,
// then against the changed snapshot. Instrument occupancy.cpp in BOTH builds
// and output_precision.cpp in the changed build; do not instrument this test.
// All precision calls remain separate TUs; use Clang after-inlining hooks.
namespace {
using namespace schgen;
using output_precision_fixture::names;
bool observing=false;
std::array<std::size_t,19> entries{};
std::size_t old_round_entries=0;
#ifndef OUTPUT_PRECISION_LEGACY
const std::array<void*,19> addresses{{
    reinterpret_cast<void*>(&floorplan_svg_extent_trunc),
    reinterpret_cast<void*>(&floorplan_svg_grid_trunc),
    reinterpret_cast<void*>(&floorplan_svg_coordinate_precision1dp),
    reinterpret_cast<void*>(&pcb_project_integer_trunc),
    reinterpret_cast<void*>(&pcb_project_class_precision4dp),
    reinterpret_cast<void*>(&pcb_silk_position_precision3dp),
    reinterpret_cast<void*>(&pcb_silk_stroke_precision3dp),
    reinterpret_cast<void*>(&ratsnest_pad_precision3dp),
    reinterpret_cast<void*>(&ratsnest_area_precision1dp),
    reinterpret_cast<void*>(&ratsnest_dispersion_precision2dp),
    reinterpret_cast<void*>(&ratsnest_budget_precision1dp),
    reinterpret_cast<void*>(&escape_ground_precision4dp),
    reinterpret_cast<void*>(&escape_scan_precision3dp),
    reinterpret_cast<void*>(&escape_copper_precision4dp),
    reinterpret_cast<void*>(&escape_coverage_precision4dp),
    reinterpret_cast<void*>(&escape_region_precision4dp),
    reinterpret_cast<void*>(&escape_port_precision4dp),
    reinterpret_cast<void*>(&escape_width_precision4dp),
    reinterpret_cast<void*>(&escape_corridor_precision4dp)}};
#define SINK , &counts
#else
#define SINK
#endif
void require(bool ok,const std::string& why){if(!ok)throw std::runtime_error(why);}
void begin(){entries={};old_round_entries=0;observing=true;}
void end(const QuantizationCounts& counts,const std::string& label,std::ostream* baseline=nullptr){
    observing=false;
    if(baseline)*baseline<<label<<" legacy_py_round_entries "<<old_round_entries<<'\n';
#ifndef OUTPUT_PRECISION_LEGACY
    QuantizationCounts actual;
    for(std::size_t i=0;i<names.size();++i)if(entries[i])actual[names[i]]=entries[i];
    require(output_precision_fixture::select(counts)==actual,label+": actual scalar entries != receipt");
    std::cerr<<label;for(const auto& [name,n]:actual)std::cerr<<' '<<name<<'='<<n;std::cerr<<'\n';
#else
    (void)counts;
#endif
}
void bytes(std::ostream& out,const std::string& name,const std::string& text){
    // Exact bytes (including diagnostic spelling), not parsed/reformatted JSON.
    out<<name<<' '<<text.size()<<'\n'<<text<<'\n';
}
PcbEscapeInput escape_input(const placement_fixture::Fixture& f,const PcbModel& m){
    auto v1=check_return_path(f.input.som_interface,f.input.return_path_footprints);
    std::map<std::string,PcbEscapeSignalClass> triage;
    for(const auto& i:m.insts)if(i.sheet.compare(0,5,"som_j")==0)
        for(const auto& [pad,n]:i.pad_nets){(void)pad;
            if(!n.second.empty()&&pcb_classify_net(n.second)=="SIGNAL")
                triage[n.second]=classify_pcb_escape_signal(n.second,f.input.function_map);
        }
    for(const auto& v:v1.violations)triage[v.net]=classify_pcb_escape_signal(v.net,f.input.function_map);
    return {m,std::move(v1),std::move(triage),f.input.interface_bytes};
}
void rats(std::ostream& out,const RatsnestGateResult& r){
    out<<r.ok<<' '<<r.cross_mm<<' '<<r.total_mm<<' '<<r.cross_budget_mm<<' '<<r.n_cross<<'\n';
    for(const auto& [name,n,a,d]:r.clusters)out<<std::quoted(name)<<' '<<n<<' '<<a<<' '<<d<<'\n';
    bytes(out,"ratsnest report",r.summary());
}
void board(std::ostream& out,const std::filesystem::path& root,const std::string& name){
    auto f=placement_fixture::load(root,name);
    const auto model=pcb_model_from_json(f.model,f.expected_pool);
    auto policy=pcb_emit_policy(f.input.floorplan.project);
    out<<"BOARD "<<name<<'\n';
    QuantizationCounts counts;
    // The placement fixture's supplied plan intentionally omits authoring-only
    // edge/connector metadata. Use its frozen notes for this rendering probe;
    // --full below separately constructs complete live notes and documents.
    const auto floor=parse_json_file((root/"native/tests/data/floorplan"/(name+".json")).string());
    std::vector<FloorplanNote> notes;
    for(const auto& n:placement_fixture::field(placement_fixture::field(floor,"expected"),"notes").array_value)
        notes.push_back({static_cast<int>(placement_fixture::number(n,"n")),placement_fixture::string(n,"block"),
                         placement_fixture::string(n,"short"),placement_fixture::string(n,"long")});
    begin();auto svg=render_floorplan_svg(f.stage.plan,notes SINK);end(counts,"svg",&out);
    bytes(out,"svg",svg);
    counts.clear();begin();auto emission=render_pcb(model,policy SINK);end(counts,"silk",&out);
    bytes(out,"pcb",emission.pcb);
    for(const auto& s:emission.diagnostics)bytes(out,"emission diagnostic",s);
    for(const auto& s:emission.fallback_events)bytes(out,"emission fallback",s);
    out<<emission.hidden_bottom_references<<' '<<emission.moved_references<<'\n';
    const auto prior=read_pcb_project(root/"native/tests/data/pcb_emit"/(name+".kicad_pro"));
    for(const auto* existing:{static_cast<const PcbProjectDocument*>(nullptr),&prior}){
        counts.clear();begin();const auto project=render_pcb_project(model,"Zynq_Carrier.kicad_pro",existing,policy SINK);
        end(counts,"project",&out);bytes(out,"project",project);
    }
    counts.clear();begin();const auto nets=ratsnest_net_pad_positions(model SINK);end(counts,"nets",&out);
    for(const auto& [net,pads]:nets){out<<std::quoted(net)<<'\n';
        for(const auto& [x,y,ref,sheet]:pads)out<<x<<' '<<y<<' '<<std::quoted(ref)<<' '<<std::quoted(sheet)<<'\n';}
    const auto edges=ratsnest_mst(nets);const PcbCheckInput check(model);
    counts.clear();begin();const auto supplied=check_ratsnest(check,&nets,&edges,default_engine_config.cross_k SINK);
    end(counts,"ratsnest supplied",&out);rats(out,supplied);
    counts.clear();begin();const auto owned=check_ratsnest(check,nullptr,nullptr,default_engine_config.cross_k SINK);
    end(counts,"ratsnest owned",&out);rats(out,owned);
    require(supplied.summary()==owned.summary(),"supplied ratsnest changed output");
    auto input=escape_input(f,model);
    counts.clear();begin();const auto copper=build_pcb_escape_copper(input SINK);end(counts,"escape copper",&out);
    floorplan_precision_fixture::node(out,copper.copper_json());
    floorplan_precision_fixture::node(out,copper.meta.json());
    counts.clear();begin();const auto plan=build_pcb_escape_plan(input SINK);end(counts,"escape plan",&out);
    floorplan_precision_fixture::node(out,plan.json());
    bytes(out,"escape block",render_pcb_escape_block(plan,copper.meta));
#ifndef OUTPUT_PRECISION_LEGACY
    const auto retained=counts;begin();
    const auto block=render_pcb_escape_block(plan,copper.meta);
    const auto report=owned.summary();end({},"cached projections");
    require(counts==retained&&report==owned.summary()&&block==render_pcb_escape_block(plan,copper.meta),
            "cached projections mutate/re-execute precision");
    // Both actual ground-pad passes must be represented, not inferred from
    // emitted vias or accepted geometry. Independent hooks above prove entries.
    // Existing validation rejects unknown copper before any silk conversion.
    auto bad=model;PcbCheckCopper unsupported;unsupported.kind="invalid-test-kind";
    bad.copper.push_back(unsupported);counts.clear();begin();bool rejected=false;
    try{(void)render_pcb(bad,policy,&counts);}catch(const PcbEmissionError& e){
        rejected=std::string(e.what()).find("unknown escape copper kind")!=std::string::npos;}
    end(counts,"early emission rejection");require(rejected&&counts.empty(),"early rejection fabricated precision");
    // Failure after an earlier instance retains the rounded pad prefix.
    auto broken=model;broken.insts.back().mod.reset();counts.clear();begin();rejected=false;
    try{(void)ratsnest_net_pad_positions(broken,&counts);}catch(const std::runtime_error&){rejected=true;}
    end(counts,"failed nets prefix");require(rejected&&!counts.empty(),"failed nets lost work");
    // Missing geometry in the last connector is a real production rejection,
    // after preceding lanes have already crossed their scalar boundaries.
    auto broken_plan=model;std::string late_net;
    for(const auto& i:model.insts)if(i.sheet=="som_j3")for(const auto& [pad,n]:i.pad_nets){
        (void)pad;if(n.first>0&&!n.second.empty()&&pcb_classify_net(n.second)=="SIGNAL")late_net=n.second;
    }
    require(!late_net.empty(),"fixture needs a J3 signal for late rejection");
    broken_plan.netclass_of[late_net]="DP_OUTPUT_TEST_NO_GEOMETRY";
    const auto broken_input=escape_input(f,broken_plan);
    counts.clear();begin();rejected=false;
    try{(void)build_pcb_escape_plan(broken_input,&counts);}catch(const PcbEscapeError& e){
        rejected=std::string(e.what()).find("has no width geometry")!=std::string::npos;}
    end(counts,"failed escape plan prefix");
    require(rejected&&counts.at("escape_port_precision4dp")>0,"failed escape plan erased earlier lanes");
    PcbProjectDocument broken_project;broken_project.data=parse_json_text("{\"untouched\":\"ok\"}");
    broken_project.data.object_value.front().second.string_value=std::string(1,static_cast<char>(0xff));
    counts.clear();begin();rejected=false;
    try{(void)render_pcb_project(model,"probe",&broken_project,policy,&counts);}catch(const PcbEmissionError& e){
        rejected=std::string(e.what()).find("invalid UTF-8")!=std::string::npos;}
    end(counts,"failed project serialization prefix");
    require(rejected&&counts.at("pcb_project_class_precision4dp")==4*(model.classes.size()+1),
            "failed project serialization erased generated class rounds");
#endif
}
void full_board(std::ostream& out,const std::filesystem::path& root,const std::string& name){
    auto fixture=placement_fixture::load(root,name);
    begin();const auto result=build_pcb_model(fixture.input);
    const auto receipt=pcb_placement_accounting(result);
    end(receipt.quantization_engagements,"full board "+name,&out);
    floorplan_precision_fixture::node(out,pcb_model_json(result.model));
    bytes(out,"full svg",result.floorplan.documents.svg);
    bytes(out,"full markdown",result.floorplan.documents.markdown);
    auto old_counts=receipt.quantization_engagements;
#ifndef OUTPUT_PRECISION_LEGACY
    old_counts=ledger_accounting_fixture::before_initial_receipt_fix(old_counts);
#endif
    for(const auto& [key,count]:placement_precision_fixture::select(output_precision_fixture::select(old_counts,false),false))
        out<<std::quoted(key)<<' '<<count<<'\n';
#ifndef OUTPUT_PRECISION_LEGACY
    const auto svg=output_precision_fixture::select(result.floorplan.documents.accounting.quantization_engagements);
    const auto escape=output_precision_fixture::select(result.placement_accounting.quantization_engagements);
    auto total=svg;checked_quantization_merge(total,escape);
    require(total==output_precision_fixture::select(receipt.quantization_engagements),"receipt owners overlap or omit work");
    begin();const auto again=pcb_placement_accounting(result);end({},"aggregate replay");
    require(again.quantization_engagements==receipt.quantization_engagements,"aggregate replay changed counts");
#endif
}
#ifndef OUTPUT_PRECISION_LEGACY
std::uint64_t bits(double x){std::uint64_t b;std::memcpy(&b,&x,sizeof b);return b;}
void scalars(){
    using Op=double(*)(double,QuantizationCounts*);
    const std::array<Op,15> ops{{pcb_project_class_precision4dp,
        pcb_silk_position_precision3dp,pcb_silk_stroke_precision3dp,ratsnest_pad_precision3dp,
        ratsnest_area_precision1dp,ratsnest_dispersion_precision2dp,ratsnest_budget_precision1dp,
        escape_ground_precision4dp,escape_scan_precision3dp,escape_copper_precision4dp,
        escape_coverage_precision4dp,escape_region_precision4dp,escape_port_precision4dp,
        escape_width_precision4dp,escape_corridor_precision4dp}};
    const std::array<int,15> digits{{4,3,3,3,1,2,1,4,3,4,4,4,4,4,4}};
    QuantizationCounts counts;
    for(std::size_t i=0;i<ops.size();++i)for(double x:{-0.,0.,1.23455,-1.23455,
            std::nextafter(1.23455,0.),std::nextafter(1.23455,2.),1e100,
            std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()}){
        const auto expected=py_round(x,digits[i]);counts.clear();begin();const auto actual=ops[i](x,&counts);
        end(counts,"round scalar");require(std::isnan(expected)?std::isnan(actual):bits(expected)==bits(actual),"round bit semantics");
    }
    for(double x:{-0.,0.,1.23455,-1.23455,std::nextafter(.1,0.),std::nextafter(.1,1.),1e100})
        for(double origin:{0.,46.,-1e100})for(double scale:{.1,6.,-1e100}){
            const auto expected=svg_map(x,origin,scale);counts.clear();begin();
            const auto actual=floorplan_svg_coordinate_precision1dp(x,origin,scale,&counts);
            end(counts,"affine scalar");require(std::isnan(expected)?std::isnan(actual):bits(expected)==bits(actual),
                    "affine rounding changed original pack.cpp FP context");
        }
    const double high=std::numeric_limits<int>::max(),low=std::numeric_limits<int>::min();
    for(double x:{-0.,0.,-1.999,1.999,high,low,high+.5,low-.5,
                  std::nextafter(high+1.,high),std::nextafter(low-1.,low)}){
        counts.clear();begin();const auto a=floorplan_svg_extent_trunc(x,&counts),b=floorplan_svg_grid_trunc(x,&counts);
        const auto c=pcb_project_integer_trunc(x,&counts);end(counts,"truncate scalar");
        require(a==static_cast<int>(x)&&b==a&&bits(c)==bits(std::trunc(x)),"truncation semantics");
    }
    for(auto op:{floorplan_svg_extent_trunc,floorplan_svg_grid_trunc})
        for(double x:{std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity(),
                      std::numeric_limits<double>::quiet_NaN(),high+1.,low-1.,
                      std::nextafter(high+1.,std::numeric_limits<double>::infinity()),
                      std::nextafter(low-1.,-std::numeric_limits<double>::infinity())}){
            counts.clear();begin();bool rejected=false;
            try{(void)op(x,&counts);}catch(const std::out_of_range&){rejected=true;}
            end(counts,"invalid scalar narrowing");require(rejected,"invalid scalar narrowing reached an integer cast");
        }
    FloorplanPlan small;small.board_w=20.9;small.board_h=30.2;
    counts.clear();begin();const auto small_svg=render_floorplan_svg(small,{},&counts);end(counts,"small grid");
    require(counts.at("floorplan_svg_extent_trunc")==2&&counts.at("floorplan_svg_grid_trunc")==5,
            "grid condition must count its two terminating conversions");
    const auto saved=counts;
    require(render_floorplan_svg(small,{})==small_svg&&counts==saved,"diagnostic rendering inherited a sink");
    for(std::size_t i=0;i<names.size();++i){
        QuantizationCounts full{{names[i],std::numeric_limits<std::size_t>::max()}};
        const auto prior=full;bool rejected=false;
        try{
            if(i==0)floorplan_svg_extent_trunc(1.,&full);
            else if(i==1)floorplan_svg_grid_trunc(1.,&full);
            else if(i==2)floorplan_svg_coordinate_precision1dp(1.,46.,6.,&full);
            else if(i==3)pcb_project_integer_trunc(1.,&full);
            else reinterpret_cast<Op>(addresses[i])(1.,&full);
        }catch(const std::overflow_error&){rejected=true;}
        require(rejected&&full==prior,"counter overflow changed receipt");
    }
    // JSON float-token short circuit is an actual skipped truncation entry.
    PcbModel model;PcbProjectDocument a,b;
    a.data=parse_json_text("{\"untouched\":1.0}");b=a;b.float_paths.insert("/untouched");
    QuantizationCounts qa,qb;
    (void)render_pcb_project(model,"probe",&a,default_pcb_emit_policy(),&qa);
    (void)render_pcb_project(model,"probe",&b,default_pcb_emit_policy(),&qb);
    require(qa.at("pcb_project_integer_trunc")==qb.at("pcb_project_integer_trunc")+1,"float token short circuit lost");
}
#endif
}
extern "C" void __cyg_profile_func_enter(void* fn,void*){
    if(!observing)return;
    if(fn==reinterpret_cast<void*>(&schgen::py_round))++old_round_entries;
#ifndef OUTPUT_PRECISION_LEGACY
    for(std::size_t i=0;i<addresses.size();++i)if(fn==addresses[i])++entries[i];
#endif
}
extern "C" void __cyg_profile_func_exit(void*,void*){}
int main(int argc,char** argv){try{
    require(argc>=2&&argc<=4,"repository root [independent baseline output] [--full]");
#ifndef OUTPUT_PRECISION_LEGACY
    scalars();
#endif
    std::ostringstream out;out<<std::hexfloat;
    board(out,argv[1],"carrier");board(out,argv[1],"devkit_mini");
    const bool full=(argc>=3&&std::string(argv[argc-1])=="--full");
    if(full){full_board(out,argv[1],"carrier");full_board(out,argv[1],"devkit_mini");}
    if(argc>=3&&std::string(argv[2])!="--full")require(out.str()==placement_fixture::read(argv[2]),"original baseline bytes/counts differ");
    else std::cout<<out.str();
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
