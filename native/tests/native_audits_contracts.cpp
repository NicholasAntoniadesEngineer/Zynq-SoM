#include "schgen/native_audit_state.hpp"
#include "schgen/quantize.hpp"
#include "verification_internal.hpp"
#include <iostream>
#include <thread>
#include <unistd.h>

std::size_t native_accounting_contracts(const std::filesystem::path&);

namespace {
using namespace schgen;
namespace fs=std::filesystem;
std::size_t checks=0;
void require(bool ok,const std::string& why){++checks;if(!ok)throw std::runtime_error(why);}
template<class F>void rejects(F fn,const std::string& why){bool thrown=false;try{fn();}catch(const std::exception&){thrown=true;}require(thrown,why);}
JsonNode number(double v){JsonNode n;n.kind=JsonKind::Number;n.number_value=v;return n;}
const JsonNode& get(const JsonNode& n,const std::string& k){const auto* p=object_field(n,k);if(!p)throw std::runtime_error("missing oracle field "+k);return *p;}
std::vector<std::string> strings(const JsonNode& n){std::vector<std::string> s;for(const auto& v:n.array_value)s.push_back(v.string_value);return s;}
struct Scratch {fs::path path;Scratch(){auto p=(fs::temp_directory_path()/"schgen_native_audit_XXXXXX").string();if(!mkdtemp(p.data()))throw std::runtime_error("mkdtemp");path=p;}~Scratch(){std::error_code e;fs::remove_all(path,e);}};
NativeLedgerDeclaration assumption(std::string name,std::string cover,double value){return {std::move(name),"ASSUME","floorplan.sizing","mm","placement pitch","standard",{std::move(cover)},{},{},false,[value]{return number(value);}};}
void ledger_contracts(const JsonNode& reference){
    NativeLedger ledger;ledger.declare(assumption("pitch","quantize.GRID_MM",1.27));
    ledger.declare({"position","CALC","floorplan.sizing","mm","placed position","",{},{"x","unit"},"round(x / unit) * unit",false,{}});
    auto pass=[&](double result){ledger.open_step("floorplan.sizing","test");ledger.calc("position",number(result),{{"x",number(2.54)},{"unit",number(1.27)}});ledger.close_step("floorplan.sizing");};
    pass(2.54);pass(2.54);pass(3.81);
    require(ledger.render()==get(reference,"render").string_value,"independent Python ledger exact render/replay");
    const auto state=ledger.audit_state();require(state.problems==strings(get(reference,"problems")),"independent replay divergence bytes");
    require(state.n_lines==get(reference,"entries").number_value,"independent ledger line count");
    const auto seen=strings(get(reference,"recorded"));require(state.recorded==std::set<std::string>(seen.begin(),seen.end()),"independent recorded decisions");
    ledger.reset();require(ledger.render().empty()&&ledger.audit_state().recorded.empty()&&ledger.audit_state().problems.empty(),"ledger reset clears replay and build state");
    rejects([&]{ledger.calc("unknown",number(0),{});},"undeclared calculation is not silently accepted");
    rejects([&]{ledger.calc("position",number(0),{{"x",number(0)},{"unit",number(1)}});},"wrong calculation step fails");
    rejects([&]{ledger.open_step("sizing.pass");},"wrong parent fails");
    rejects([&]{ledger.open_step("made-up");},"unknown step fails");
    ledger.open_step("floorplan.sizing");require(!ledger.audit_state().problems.empty(),"unclosed step is a gate problem");
    rejects([&]{ledger.calc("position",number(0),{{"unit",number(1)},{"x",number(0)}});},"ordered input drift fails");
    rejects([&]{ledger.close_step("netlist");},"wrong close fails");
    ledger.calc("position",number(1),{{"x",number(1)},{"unit",number(1)}});
    ledger.calc("position",number(2),{{"x",number(2)},{"unit",number(1)}});
    ledger.close_step("floorplan.sizing");require(ledger.audit_state().problems==std::vector<std::string>{"calculation 'position' recorded more than once"},"duplicate decision persists as failure");
    rejects([&]{ledger.declare(assumption("late","x",0));},"registry sealed during build");
    NativeLedger live;double pitch=1.27;auto d=assumption("pitch","live::pitch",0);d.resolve=[&]{return number(pitch);};live.declare(d);
    live.open_step("floorplan.sizing");live.close_step("floorplan.sizing");live.reset();pitch=2.54;live.open_step("floorplan.sizing");
    require(live.render().find("2.54")!=std::string::npos,"live provider honors changed caller values");live.close_step("floorplan.sizing");
    NativeLedger broken;d.name="throws";d.resolve=[]()->JsonNode{throw std::runtime_error("resolver failed");};broken.declare(d);
    rejects([&]{broken.open_step("floorplan.sizing");},"live resolver exception propagates");require(!broken.audit_state().problems.empty(),"failed step cannot produce a passing gate");
}
void registry_contracts(const JsonNode& reference){
    NativeFallbacks f;register_native_fallbacks(f);f.record("seat_node_budget");const auto snap=f.snapshot();f.record("seat_node_budget");f.restore(snap);
    const auto census=f.census();require(census.size()==get(reference,"census").object_value.size(),"native fallback registry owns all captured paths");
    for(const auto& [name,v]:get(reference,"census").object_value)require(census.at(name)==AuditInteger(std::int64_t(v.number_value)),"independent rollback census "+name);
    rejects([&]{f.record("not-registered");},"unknown fallback is an error");rejects([&]{register_native_fallbacks(f);},"duplicate fallback registration fails");
    rejects([&]{f.restore({"not-registered"});},"bad restore fails before state mutation");require(f.snapshot()==snap,"failed restore preserves events");
    f.reset();require(f.census().at("seat_node_budget")==AuditInteger{},"fallback reset keeps zero registrations");
    NativeQuantizations q;register_native_quantizations(q);require(q.declarations().size()==20,"15 original registrations, three grid helpers, exact step boundary and native refit precision");
    rejects([&]{register_native_quantizations(q);},"duplicate transform registration fails");
    const std::vector<double> values={-100.13,-2.5,-0.635,-0.25,0,0.05,0.635,1.2345,83.15};
    for(double value:values){
        require(q.invoke("fixed_part_grid",{value})==fixed_part_grid(value),"grid caller value");
        require(q.invoke("evict_corridor_grid",{3.173,value})==evict_corridor_grid(3.173,value),"origin parameter is retained");
        require(q.invoke("breathe_anchor_grid",{value})==fixed_part_grid(value),"breathe numeric implementation");
        require(q.invoke("outline_fine_grid",{value,3})==fine_shrink(value,3),"fine base and step preserved");
        for(double unit:{0.125,0.7,2.54}){
            require(q.invoke("gsnap",{value,unit})==gsnap(value,unit),"caller gsnap unit preserved");
            require(q.invoke("gfloor",{value,unit})==gfloor(value,unit),"caller gfloor unit preserved");
            require(q.invoke("gceil",{value,unit})==gceil(value,unit),"caller gceil unit preserved");
        }
    }
    require(q.invoke("seat_slide",{})==1.2&&q.invoke("run_overflow_tol",{})==0.1,"native scalar transform policies");
    require(q.invoke("est_via_cost",{0})==2.2&&q.invoke("est_via_cost",{1})==7.6,"native boolean class selection");
    rejects([&]{q.invoke("outline_grow_step",{0.5});},"no silent fractional integer narrowing");
    rejects([&]{q.invoke("checked_integer_step",{double(INT64_MAX)});},"no out-of-range integer narrowing");
    require(q.invoke("checked_integer_step",{-3})==-3,"exact integer boundary preserves caller step");
    rejects([&]{q.invoke("fixed_part_grid",{});},"arity error propagates");
    rejects([&]{q.invoke("invented",{1});},"unregistered transform fails");
    q.reset_engagements();std::vector<std::thread> workers;
    for(int i=0;i<4;++i)workers.emplace_back([&]{for(int j=0;j<100;++j){q.invoke("fixed_part_grid",{double(j)});f.record("seat_node_budget");}});
    for(auto& worker:workers)worker.join();require(q.engagements().at("fixed_part_grid")==AuditInteger(400),"concurrent native engagements are not lost");require(f.census().at("seat_node_budget")==AuditInteger(400),"concurrent fallback events are not lost");
    q.declare({"error","errors.cpp::error","throws","failure propagation","pre-proof",0,[](const auto&)->double{throw std::domain_error("original error");}});
    rejects([&]{q.invoke("error",{});},"transform evaluation errors propagate");require(q.engagements().at("error")==AuditInteger(1),"attempted transform counted even when it throws");
}
void ratchet_contracts(const JsonNode& reference,const fs::path& scratch){
    std::size_t i=0;
    for(const auto& row:get(reference,"fallback").array_value){
        const auto path=scratch/("ratchet-"+std::to_string(i++)+".json");
        const auto& baseline=get(row,"baseline");if(baseline.kind!=JsonKind::Null)model_checks::publish(path,baseline.string_value);
        AuditCounts census;for(const auto& [name,v]:get(row,"census").object_value)census[name]=v.kind==JsonKind::String?AuditInteger::decimal(v.string_value):AuditInteger(std::int64_t(v.number_value));
        const auto result=check_fallback_ratchet(census,path);const auto& expected=get(row,"result");
        require(result.ok==get(expected,"ok").bool_value&&result.pinned==get(expected,"pinned").bool_value,"independent fallback pin/regression verdict");
        require(result.n_names==get(expected,"n_names").number_value&&result.n_fired==get(expected,"n_fired").number_value,"independent fallback totals");
        require(result.regressions==strings(get(expected,"regressions")),"independent fallback findings");
        require(result.summary()==get(row,"summary").string_value,"independent fallback report bytes");
        require(model_checks::read(path)==get(row,"after").string_value,"independent fallback write/no-write exact bytes");
    }
    NativeFallbacks owned;register_native_fallbacks(owned);owned.record("seat_node_budget");
    const auto path=scratch/"owned-ratchet.json";require(check_fallback_ratchet(owned.census(),path).pinned,"ratchet consumes owned live state");
    const auto pinned=model_checks::read(path);owned.record("seat_node_budget");require(!check_fallback_ratchet(owned.census(),path).ok,"extra actual fallback fires regression");
    require(model_checks::read(path)==pinned,"native regression cannot rewrite its ceiling");
    const auto blocked=scratch/"blocked";model_checks::publish(blocked,"not a directory");rejects([&]{check_fallback_ratchet(owned.census(),blocked/"ceiling.json");},"native baseline write errors propagate");
}
const std::string green="namespace policy {\nconstexpr double pitch=1.25;\ndouble snap(double x){return __builtin_round(x/pitch)*pitch;}\ndouble place(double x){return x+pitch;}\n}\n";
void source_contracts(const fs::path& root,const fs::path& scratch){
    NativeLedger ledger;ledger.declare(assumption("pitch","geometry.cpp::policy::pitch",1.25));ledger.open_step("floorplan.sizing");ledger.close_step("floorplan.sizing");
    NativeQuantizations q;q.declare({"snap","geometry.cpp::policy::snap","round(x/pitch)*pitch","Snap before proving placement.","pre-proof",1,[](const auto& a){return std::round(a[0]/1.25)*1.25;}});
    const auto path=scratch/"geometry.cpp";model_checks::publish(path,green);
    auto scan=[&]{return scan_cpp_audit_sources(scratch,{{"geometry.cpp"}});};
    auto result=check_native_audits(scan(),ledger,q);require(result.ok,"live C++ green audit: "+result.summary());require(result.n_constants==1,"green registry does not invent constants");
    const std::vector<std::pair<std::string,std::string>> mutations={
        {"namespace policy { constexpr double smuggled=4.2; }\n","constant"},
        {"namespace policy { double f(double x){constexpr double hidden=4.2;return x+hidden;} }\n","buried"},
        {"namespace policy { double f(double x){double HIDDEN_GAP=4.2;return x+HIDDEN_GAP;} }\n","buried"},
        {"namespace policy { double f(double x){double ΔΙΑΚΕΝΟ=4.2;return x+ΔΙΑΚΕΝΟ;} }\n","buried"},
        {"namespace policy { struct Bounds {static constexpr double margin=4.2;}; }\n","buried"},
        {"namespace policy { struct Bounds {double margin=4.2;}; }\n","buried"},
        {"namespace policy { enum { UNDECLARED=8 }; }\n","constant"},
        {"namespace policy { double bad(double gap){return __builtin_round(gap);} }\n","raw-round"},
        {"namespace policy { double bad(double gap){return __builtin_floor(gap);} }\n","raw-round"},
        {"namespace policy { double round(double);double bad(double gap){auto alias=&round;return alias(gap);} }\n","raw-round"},
        {"namespace policy { double bad(double gap){return static_cast<int>(gap/2)*2;} }\n","float-to-integer"},
        {"namespace policy { double bad(double gap){int n=gap;return n;} }\n","float-to-integer"},
        {"namespace policy { double bad(double gap){return (int)(gap/2)*2;} }\n","float-to-integer"},
        {"namespace policy { double bad(double gap){return gap-0.05;} }\n","credit-0.05"},
        {"namespace policy { constexpr double GRID=2; }\n","banned-constant"},
        {"namespace policy { double _r5(double);double bad(double x){return _r5(x);} }\n","banned-call"},
        {"#define HIDDEN_ROUND(x) __builtin_round(x)\nnamespace policy { double bad(double gap){return HIDDEN_ROUND(gap);} }\n","raw-round"},
        {"#define HIDDEN_CONSTANT constexpr double hidden_macro=3.5;\nnamespace policy { HIDDEN_CONSTANT }\n","constant"}
        ,{"#define HIDDEN_PITCH 3.5\nnamespace policy { double bad(double x){return x*HIDDEN_PITCH;} }\n","constant"}
    };
    for(const auto& [mutation,detector]:mutations){model_checks::publish(path,green+mutation);result=check_native_audits(scan(),ledger,q);
        require(!result.ok,"real C++ mutation must fail: "+mutation);
        if(detector=="constant")require(!result.undeclared.empty(),"unregistered declaration detector");
        else if(detector=="buried")require(!result.buried.empty(),"buried constant detector");
        else require(std::any_of(result.unregistered_quantization.begin(),result.unregistered_quantization.end(),[needle="["+detector+"]"](const auto& s){return s.find(needle)!=s.npos;}),"mutation owns intended detector "+detector+": "+result.summary());
    }
    model_checks::publish(path,"// constexpr double fake=4; std::round(gap);\n"+green+"const char* prose=R\"(GRID = 2; int(gap/2)*2;)\";\n");require(check_native_audits(scan(),ledger,q).ok,"comments/string text is not code");
    require(check_native_audits(scratch,{{"geometry.cpp"}},ledger,q).ok,"production gate performs a live compiler scan");
    NativeLedger absent;absent.declare(assumption("pitch","geometry.cpp::policy::pitch",1.25));require(!check_native_audits(scan(),absent,q).absent.empty(),"C++ gate consults actual owned recorded state");
    model_checks::publish(path,"namespace policy { double place(double x){return x;} }\n");result=check_native_audits(scan(),ledger,q);require(result.stale.size()==2,"deleted C++ constant AND transform are stale");
    model_checks::publish(path,green+"double broken( {\n");rejects(scan,"compiler syntax errors propagate");
    model_checks::publish(path,green+"static_assert(AUDIT_FLAG==9);\n");rejects(scan,"missing caller define is not silently bypassed");
    CppAuditOptions flags;flags.flags={"-DAUDIT_FLAG=9"};require(check_native_audits(scan_cpp_audit_sources(scratch,{{"geometry.cpp"}},flags),ledger,q).ok,"caller compiler defines preserved");
    rejects([&]{scan_cpp_audit_sources(scratch,{});},"empty manifest cannot yield fake pass");
    rejects([&]{scan_cpp_audit_sources(scratch,{{"missing.cpp"}});},"missing source cannot be skipped");
    rejects([&]{scan_cpp_audit_sources(scratch,{{"geometry.cpp"},{"geometry.cpp"}},flags);},"duplicate source manifest rejected");
    CppAuditOptions no_compiler;no_compiler.compiler="/nonexistent/native-audit-compiler";rejects([&]{scan_cpp_audit_sources(scratch,{{"geometry.cpp"}},no_compiler);},"missing compiler cannot pass");
    // Real production C++ translation unit: no Python input, grammar or fixture
    // source. All raw operations must be inside an explicitly registered body.
    CppAuditOptions live;live.flags={"-I"+(root/"native/include").string()};
    const auto census=scan_cpp_audit_sources(root,{{"native/include/schgen/quantize.hpp"},{"native/src/quantize.cpp"},{"native/src/native_audit_quantize.cpp"}},live);
    require(census.constants.size()==8&&census.functions.size()==20,"actual native quantize declarations are scanned");
    NativeQuantizations all;register_native_quantizations(all);
    NativeLedger live_ledger;
    const std::vector<std::pair<std::string,double>> constants={{"kGridMm",fixed_part_grid(1.3)},{"kHalfMm",som_pose_half_mm(0.7)},{"kCreditMm",quant_credit(0)},
        {"kSnapErosionMm",snap_erosion_pad(5)-5},{"kOutlineSnapMm",outline_grow(1)},{"kFineSnapMm",fine_shrink(2,1)},{"kViaOrdinaryMm",est_via_cost(false)},{"kViaImpedanceMm",est_via_cost(true)}};
    for(const auto& [name,value]:constants)live_ledger.declare(assumption(name,"native/include/schgen/quantize.hpp::schgen::quantization_policy::"+name,value));
    live_ledger.open_step("floorplan.sizing");live_ledger.close_step("floorplan.sizing");
    const auto audited=check_native_audits(census,live_ledger,all);require(audited.ok,"production quantize C++ policy audit: "+audited.summary());
    model_checks::publish(path,"");rejects([&]{check_native_audits(scratch,{{"geometry.cpp"}},NativeLedger{},NativeQuantizations{});},"empty translation unit cannot fake a gate pass");
}
}
int main(int argc,char** argv){try{
    require(argc==2||(argc==3&&std::string(argv[2])=="--sources-only"),"usage: native_audits_contracts <repo-root> [--sources-only]");const fs::path root=fs::absolute(argv[1]);Scratch tmp;
    if(argc==3){source_contracts(root,tmp.path);std::cout<<"Native C++ source audits: "<<checks<<" contracts passed\n";return 0;}
    const auto reference=parse_json_file((root/"native/tests/data/verification_audits/python_state.json").string());
    ledger_contracts(reference);registry_contracts(reference);
    ratchet_contracts(parse_json_file((root/"native/tests/data/verification_audits/fallback_reference.json").string()),tmp.path);
    const auto integers=parse_json_file((root/"native/tests/data/verification_audits/integer_reference.json").string());
    for(const auto& row:get(integers,"cases").array_value){const auto input=get(row,"input").string_value;
        if(object_field(row,"error"))rejects([&]{AuditInteger::decimal(input);},"independent invalid integer whitespace");
        else require(AuditInteger::decimal(input).str()==get(row,"value").string_value,"independent Unicode decimal integer");
    }
    source_contracts(root,tmp.path);
    checks+=native_accounting_contracts(root);
    std::cout<<"Native state/C++ audits: "<<checks<<" contracts passed; real C++ source mutations rejected\n";return 0;
}catch(const std::exception& e){std::cerr<<"Native audits FAILED: "<<e.what()<<'\n';return 1;}}
