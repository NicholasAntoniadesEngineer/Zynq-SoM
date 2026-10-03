// Reuse the frozen floorplan decoder and its strict assertions, not live inputs.
#define main frozen_floorplan_contracts_unused_main
#include "floorplan_contracts.cpp"
#undef main
#include <cstring>
#include "floorplan_fixed_choice_fixture.hpp"

// This executable instruments only the unchanged floorplan_geometry.cpp.
// Supported ABI: GNU/Clang Itanium, non-virtual member, zero this adjustment.
// Entries independently count real calls; exits copy the newly recorded name
// BEFORE orchestration can discard it. No production hook or source rewrite.
#if !defined(__GXX_ABI_VERSION) || !(defined(__clang__) || defined(__GNUC__))
#error "fallback scope observer requires the GNU/Clang Itanium C++ ABI"
#endif
namespace scope_test {
thread_local Engine* active=nullptr;
thread_local bool enabled=false,busy=false,observer_failed=false;
thread_local std::size_t entries=0,exits=0;
thread_local std::vector<std::string> observed;
void* watched=nullptr;
bool mismatch=false;
void setup(){
    struct Member {void* code;std::ptrdiff_t adjustment;};
    const auto method=&Engine::fallback;
    static_assert(sizeof(method)==sizeof(Member),"unsupported member pointer ABI");
    Member member{};std::memcpy(&member,&method,sizeof member);
    require(member.code&&member.adjustment==0,"nonvirtual unadjusted fallback method ABI");
    watched=member.code;
}
void begin(Engine* engine){active=engine;entries=exits=0;observed.clear();observer_failed=false;enabled=true;}
void stop(){enabled=false;active=nullptr;require(!observer_failed,"observer completed without exception");require(entries==exits,"every observed fallback entry completed");}
void receipt(const std::string& label,const std::vector<std::string>& prefix,const std::vector<std::string>& actual){
    auto wanted=prefix;wanted.insert(wanted.end(),observed.begin(),observed.end());
    const bool exact=actual==wanted;mismatch|=!exact;
    std::cout<<label<<": entries="<<entries<<" observed="<<observed.size()<<" exact="<<exact<<'\n';
    require(entries==observed.size(),"independent entries equal independently retained exit identities");
}
FloorplanInput frozen(const std::filesystem::path& root,const char* project){
    return input(field(parse_json_file((root/"native/tests/data/floorplan"/(std::string(project)+".json")).string()),"input"));
}
std::string without_events(FloorplanPlan value){
    value.accounting.fallback_events.clear();std::ostringstream out;
    floorplan_precision_fixture::node(out,floorplan_plan_json(value));out<<render_floorplan_ledger(value);return out.str();
}
void defaults(const std::filesystem::path& root,std::ostream& dump){
    for(const char* project:{"carrier","devkit_mini"}){
        auto in=frozen(root,project);const auto unchanged=in.accounting.fallback_events;
        Engine engine(in);begin(&engine);auto result=engine.run();stop();
        require(entries>0,"frozen defaults execute fallback work");
        receipt(project,unchanged,result.accounting.fallback_events);
        require(in.accounting.fallback_events==unchanged,"input prefix is immutable");
        dump<<project<<'\n'<<without_events(result);
        // Deliberately duplicated, ordered prefix including the same names as
        // new work: neither deduplication nor regrouping is permitted.
        result.accounting.fallback_events={"interior_reseat_retry","legalize_only_compaction","interior_reseat_retry"};
        engine.plan=result;begin(&engine);engine.choose_connector_shapes();stop();
        require(entries>0,"connector rejection replay executes fallback work");
        receipt(std::string(project)+"/connector",result.accounting.fallback_events,engine.plan.accounting.fallback_events);
        dump<<project<<"/connector\n"<<without_events(engine.plan);
    }
    auto in=frozen(root,"devkit_mini");if(!in.spec)in.spec=FloorplanSpec{};in.spec->outline={{100,100}};
    Engine fixed(in);begin(&fixed);const auto result=fixed.run();stop();
    require(entries>0,"fixed frozen solve executes actual fallback work");
    receipt("devkit_mini/fixed",in.accounting.fallback_events,result.accounting.fallback_events);
    dump<<"devkit_mini/fixed\n"<<without_events(result);
}
FloorplanInput free_input(){
    FloorplanInput in;in.som.w=in.som.h=20;in.spec=FloorplanSpec{};
    CircuitSheetIr sc;sc.name="logic";
    sc.parts.push_back({"R1","Device:R","10k","Resistor_SMD:R_0603_1608Metric",{},{},{}});in.sheets={sc};
    in.geometry.zone_box["logic"]={12,8};FloorplanZoneShape top;top.w=12;top.h=8;auto bottom=top;bottom.side="bottom";
    in.geometry.shapes["logic"]={top,bottom};in.spec->interior["logic"].layer="bottom";
    in.accounting.fallback_events={"legalize_only_compaction","interior_reseat_retry","legalize_only_compaction"};return in;
}
void free_wins(std::ostream& dump,bool fixed){
    auto in=fixed?fixed_choice_fixture::input():free_input();
    in.accounting.fallback_events={"legalize_only_compaction","interior_reseat_retry","legalize_only_compaction"};
    const auto control=build_floorplan(in);require(control.punch_free,"natural free-pass winner");
    auto experiment=std::make_shared<FloorplanExperiment>();in.experiment=experiment;Engine engine(in);
    std::array<bool,2> injected{};
    // Controlled receipt-only sentinels, NOT claimed as real retry episodes:
    // exercise both pass boundaries even though this tiny packing needs none.
    experiment->attempt_completed=[&](const FloorplanAttemptObservation& row){
        auto& done=injected[row.punch_free?1:0];if(done)return;done=true;
        engine.fallback(row.punch_free?"interior_reseat_retry":"legalize_only_compaction");
    };
    begin(&engine);const auto result=engine.run();stop();
    require(injected[0]&&injected[1]&&result.punch_free,"both passes executed, free wins");
    require(observed==std::vector<std::string>{"legalize_only_compaction","interior_reseat_retry"},"controlled pass sentinels in execution order");
    receipt(fixed?"fixed-free-win":"auto-free-win",in.accounting.fallback_events,result.accounting.fallback_events);
    require(without_events(result)==without_events(control),"receipt-only sentinels cannot change geometry or actual-work counters");
    dump<<(fixed?"fixed-free-win\n":"auto-free-win\n")<<without_events(result);
}
struct InjectedFailure:std::runtime_error {InjectedFailure():std::runtime_error("test failure after fallback in free pass"){} };
void failure(const std::filesystem::path& root,bool fixed){
    auto in=frozen(root,"devkit_mini");if(fixed){if(!in.spec)in.spec=FloorplanSpec{};in.spec->outline={{100,100}};}
    in.accounting.fallback_events.insert(in.accounting.fallback_events.begin(),{"interior_reseat_retry","legalize_only_compaction","interior_reseat_retry"});
    const auto prefix=in.accounting.fallback_events;
    auto experiment=std::make_shared<FloorplanExperiment>();in.experiment=experiment;
    experiment->attempt_completed=[](const FloorplanAttemptObservation& row){if(row.punch_free&&entries>0)throw InjectedFailure();};
    Engine engine(in);bool rejected=false;begin(&engine);
    try{(void)engine.run();}catch(const InjectedFailure&){rejected=true;}stop();
    require(rejected&&entries>0,"injected failure occurs after actual fallback calls");
    receipt(fixed?"fixed-failure":"auto-failure",prefix,engine.plan.accounting.fallback_events);
    const auto calls=entries;const auto expected=engine.plan.accounting;
    // Repeat through the PUBLIC transport. Entry counts remain independent;
    // the directly observed run supplies event identities and exact ordering.
    ExecutionFailureReceipt failed;rejected=false;begin(nullptr);
    try{(void)build_floorplan(in,&failed);}catch(const InjectedFailure&){rejected=true;}stop();
    require(rejected&&entries==calls&&failed.captured&&!failed.unavailable,"public failure transport captures identical executed prefix");
    require(failed.accounting.fallback_events==expected.fallback_events&&failed.accounting.quantization_engagements==expected.quantization_engagements,"public receipt preserves exact events and actual-work counters");
    require(in.accounting.fallback_events==prefix,"failure never mutates incoming prefix");
}
}
extern "C" void __cyg_profile_func_enter(void* function,void*){
    using namespace scope_test;if(enabled&&!busy&&function==watched)++entries;
}
extern "C" void __cyg_profile_func_exit(void* function,void*){
    using namespace scope_test;if(!enabled||busy||function!=watched)return;++exits;
    if(!active)return;busy=true;
    try{if(active->plan.accounting.fallback_events.empty())observer_failed=true;else observed.push_back(active->plan.accounting.fallback_events.back());}catch(...){observer_failed=true;}
    busy=false;
}
int main(int argc,char** argv){try{
    require(argc==2||argc==3,"usage: fallback_scope_contracts ROOT [private nonfallback dump]");
    scope_test::setup();std::ostringstream dump;scope_test::defaults(argv[1],dump);
    scope_test::free_wins(dump,false);scope_test::free_wins(dump,true);
    scope_test::failure(argv[1],false);scope_test::failure(argv[1],true);
    if(argc==3){std::ofstream file(argv[2],std::ios::binary);file<<dump.str();require(bool(file),"write private nonfallback dump");}
    require(!scope_test::mismatch,"all incoming prefixes plus observed fallback calls retained EXACTLY in order");
    std::cout<<"fallback scope contracts PASS\n";
}catch(const std::exception& error){scope_test::enabled=false;std::cerr<<error.what()<<'\n';return 1;}}
