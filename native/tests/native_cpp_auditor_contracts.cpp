#include "schgen/native_audit_state.hpp"
#include "schgen/atomic_file.hpp"
#include <cmath>
#include <iostream>
#include <unistd.h>

namespace fs=std::filesystem;
using namespace schgen;
namespace {
std::size_t checks=0;
void require(bool ok,const std::string& why){++checks;if(!ok)throw std::runtime_error(why);}
struct Scratch {
    fs::path path;
    Scratch(){auto value=(fs::temp_directory_path()/"schgen-cpp-auditor-XXXXXX").string();if(!::mkdtemp(value.data()))throw std::runtime_error("mkdtemp");path=value;}
    ~Scratch(){std::error_code e;fs::remove_all(path,e);}
};
void write(const fs::path& path,const std::string& text){write_atomic_file(path.string(),{text.begin(),text.end()});}
JsonNode number(double v){JsonNode n;n.kind=JsonKind::Number;n.number_value=v;return n;}
void cover(NativeLedger& ledger,const std::string& name,const std::string& symbol,double value){
    NativeLedgerDeclaration d;d.name=name;d.kind="ASSUME";d.step="floorplan.sizing";d.source="policy";
    d.basis="Explicit independent compiler-fixture policy";d.covers={symbol};d.resolve=[value]{return number(value);};ledger.declare(d);
}
void record(NativeLedger& ledger){ledger.open_step("floorplan.sizing");ledger.close_step("floorplan.sizing");}
void transform(NativeQuantizations& q,const std::string& name,const std::string& symbol){
    q.declare({name,symbol,"round(x)","Actual scalar round operation in the compiler fixture","pre-proof",1,
        [](const std::vector<double>& a){return std::round(a.at(0));}});
    require(q.invoke(name,{1.6})==2&&q.invoke(name,{-1.6})==-2,"fixture callback evaluates the actual scalar operation");
}
bool symbol(const CppSourceCensus& c,const std::string& suffix){
    return std::any_of(c.constants.begin(),c.constants.end(),[&](const auto& x){return x.symbol=="policy.cpp::policy::"+suffix;});
}
void source_contracts(){
    Scratch tmp;NativeLedger empty;NativeQuantizations none;
    auto scan=[&](const std::string& source){write(tmp.path/"policy.cpp",source);return scan_cpp_audit_sources(tmp.path,{{"policy.cpp"}});};
    auto c=scan("namespace policy { double estimate(){return 0;} double estimate(int n){return n;} }\n");
    require(c.functions.size()==2,"unrelated overloads keep distinct implementations without aborting");
    require(check_native_audits(c,empty,none).ok,"unrelated overloads need no transform registration");
    c=scan("namespace policy { struct State { double area=0; int count{}; double margin=0.0; double offset=-0.0; }; double use(State s){return s.area;} }\n");
    require(c.constants.empty(),"mutable zero/value-initialized instance state is not policy storage");
    require(check_native_audits(c,empty,none).ok,"ordinary instance state passes");
    c=scan("namespace policy { struct State { char edge='\\0'; signed char face=0; unsigned char side{}; }; }\n");
    require(c.constants.empty(),"Clang numeric character zero is ordinary mutable state");
    c=scan("namespace policy { struct State {char edge='N'; char width='\\4'; const char frozen='\\0'; static constexpr char pitch='\\0';}; }\n");
    for(const auto& s:{"State::edge","State::width","State::frozen","State::pitch"})
        require(symbol(c,s),std::string("nonzero or immutable character storage remains policy: ")+s);
    require(check_native_audits(c,empty,none).buried.size()==4,"character zero correction does not waive nonzero or immutable policy");
    c=scan("namespace policy { struct Limits { double margin=4.2; const double frozen=0; static constexpr double pitch=1.25; }; double f(){static double clearance=.3;constexpr double eps=1e-9;double HIDDEN_GAP=4.2;return eps+HIDDEN_GAP+clearance;} }\n");
    for(const auto& s:{"Limits::margin","Limits::frozen","Limits::pitch","f::clearance","f::eps","f::HIDDEN_GAP"})
        require(symbol(c,s),std::string("hidden engineering storage remains visible: ")+s);
    require(check_native_audits(c,empty,none).buried.size()==6,"all six uncovered hidden constants fail");
    NativeLedger exact;cover(exact,"pitch","policy.cpp::policy::Limits::pitch",1.25);record(exact);
    auto r=check_native_audits(c,exact,none);
    require(r.buried.size()==5&&r.stale.empty(),"exact buried cover works without covering siblings");
    c=scan("namespace policy { struct Limits {static constexpr double pitch=1.25;}; double apply(double x){return x*Limits::pitch;} }\n");
    require(check_native_audits(c,exact,none).ok,"one authored exact class policy cover passes");
    NativeLedger absent;cover(absent,"pitch","policy.cpp::policy::Limits::pitch",1.25);
    require(!check_native_audits(c,absent,none).absent.empty(),"a cover without live recording does not pass");
    c=scan("namespace policy { struct Limits {static constexpr double changed=1.25;}; double apply(double x){return x;} }\n");
    r=check_native_audits(c,exact,none);require(!r.stale.empty()&&!r.buried.empty(),"renaming covered storage creates stale cover and new finding");
    const std::string overloaded="namespace policy { double snap(double x){return __builtin_round(x);} double snap(int x){return __builtin_round(x);} }\n";
    c=scan(overloaded);
    require(c.functions.count("policy.cpp::policy::snap [double (double)]")&&c.functions.count("policy.cpp::policy::snap [double (int)]"),"overload signatures remain individually addressable");
    NativeQuantizations ambiguous;transform(ambiguous,"snap","policy.cpp::policy::snap");
    r=check_native_audits(c,empty,ambiguous);
    require(!r.ok&&!r.stale.empty()&&!r.unregistered_quantization.empty(),"short ambiguous transform never covers either overload");
    NativeQuantizations one;transform(one,"snap-double","policy.cpp::policy::snap [double (double)]");
    r=check_native_audits(c,empty,one);require(!r.ok&&r.stale.empty(),"exact double registration leaves integer overload raw");
    for(const auto& finding:r.unregistered_quantization)require(finding.find("[double (int)]")!=finding.npos,"remaining finding belongs to the unregistered overload");
    c=scan("namespace policy { double snap(double x){return __builtin_round(x);} double snap(int x){return x;} }\n");
    require(check_native_audits(c,empty,one).ok,"exact registered overload covers only its actual body");
    // Out-of-line definitions must use the semantic class context from Clang,
    // not the surrounding namespace in which the definition is written.
    c=scan("namespace policy { struct A {double f(double) const;double f(int);}; struct B {double f(double) const;}; double A::f(double x) const{return x;} double A::f(int x){return x;} double B::f(double x) const{return x;} }\n");
    require(c.functions.count("policy.cpp::policy::A::f [double (double) const]")&&c.functions.count("policy.cpp::policy::A::f [double (int)]"),"out-of-line class overload identity");
    require(c.functions.count("policy.cpp::policy::B::f"),"unrelated class method is not collapsed into another class");
    c=scan("namespace policy { double f(double x){constexpr double gap=2.5;return x+gap;} double f(int x){constexpr double gap=3.5;return x+gap;} }\n");
    require(symbol(c,"f [double (double)]::gap")&&symbol(c,"f [double (int)]::gap"),"overloaded local constants have separate exact covers");
    NativeLedger local;cover(local,"double-gap","policy.cpp::policy::f [double (double)]::gap",2.5);record(local);
    r=check_native_audits(c,local,none);require(r.buried.size()==1&&r.stale.empty()&&r.buried.front().find("[double (int)]")!=std::string::npos,"cover cannot leak between overloaded local policies");
    c=scan("namespace policy { constexpr double GRID=0; double f(double x){return x;} }\n");
    NativeLedger banned;cover(banned,"grid","policy.cpp::policy::GRID",0);record(banned);
    require(!check_native_audits(c,banned,none).unregistered_quantization.empty(),"constant coverage cannot waive a banned precision operation");
    c=scan("namespace policy { double snap(double x){auto f=[](double y){return __builtin_round(y);};return f(x);} }\n");
    NativeQuantizations outer;transform(outer,"outer","policy.cpp::policy::snap");
    require(!check_native_audits(c,empty,outer).unregistered_quantization.empty(),"nested lambda precision is not the registered scalar implementation body");
    c=scan("namespace policy { struct A {double f(double);}; double A::f(double x){const double eps=.1;return x+eps;} }\n");
    require(symbol(c,"A::f::eps"),"local policy belongs to its out-of-line class method");
    write(tmp.path/"policy.hpp","namespace policy { struct Engine {double estimate();double estimate(int);}; }\n");
    c=scan("#include \"policy.hpp\"\nnamespace policy {double Engine::estimate(){return 0;}double Engine::estimate(int n){return n;} }\n");
    require(c.functions.count("policy.cpp::policy::Engine::estimate [double ()]")&&c.functions.count("policy.cpp::policy::Engine::estimate [double (int)]"),"included class declaration supplies out-of-line semantic identity");
    c=scan("#include \"policy.hpp\"\nnamespace policy {double Engine::estimate(){return estimate(1);}double Engine::estimate(int n){auto position=[](double x){return x;};auto pad=[](double x){return __builtin_round(x);};return position(n)+pad(n);} }\n");
    require(c.functions.size()==4&&c.functions.count("policy.cpp::policy::Engine::estimate [double ()]")&&c.functions.count("policy.cpp::policy::Engine::estimate [double (int)]"),"two exact overloads stay addressable alongside their nested wrappers");
    require(std::count_if(c.functions.begin(),c.functions.end(),[](const auto& name){return name.find("policy.cpp::policy::Engine::estimate [double (int)]::<lambda@")==0;})==2,"both nested wrapper identities remain in the census");
    r=check_native_audits(c,empty,none);
    require(!r.unregistered_quantization.empty()&&std::all_of(r.unregistered_quantization.begin(),r.unregistered_quantization.end(),[](const auto& finding){return finding.find("Engine::estimate [double (int)]::<lambda@")!=finding.npos;}),"nested wrapper precision remains independently unregistered");
    c=scan("namespace policy { struct A {double f(double) & {return 1;}double f(double) const & {return 2;}double f(double) && {return 3;}}; }\n");
    require(c.functions.size()==3&&c.functions.count("policy.cpp::policy::A::f [double (double) const &]"),"cv/ref-qualified overloads retain separate identities");
    c=scan("namespace policy { using Distance=double; struct State {Distance area=0;Distance hidden=.4;const Distance frozen=0;}; double f(){return 0;} }\n");
    require(c.constants.size()==2&&symbol(c,"State::hidden")&&symbol(c,"State::frozen"),"numeric aliases do not hide engineering defaults or const zero policy");
    c=scan("namespace policy { double f(double x){if(x>0){constexpr double gap=2.5;return x+gap;}else{constexpr double gap=3.5;return x+gap;}} }\n");
    NativeLedger shadow;cover(shadow,"gap","policy.cpp::policy::f::gap",2.5);record(shadow);
    r=check_native_audits(c,shadow,none);
    require(!r.ok,"one ambiguous local name cannot cover different block-scope policies");
    require(c.constants.size()==2&&c.constants[0].symbol!=c.constants[1].symbol,"block shadows have different exact identities");
    const auto first_offset=std::string("namespace policy { double f(double x){if(x>0){constexpr double ").size();
    NativeLedger first_shadow;cover(first_shadow,"gap","policy.cpp::policy::f::gap [at "+std::to_string(first_offset)+"]",2.5);record(first_shadow);
    r=check_native_audits(c,first_shadow,none);
    require(r.buried.size()==1&&r.stale.empty(),"authored exact block cover cannot cover its sibling");
}
void production_contracts(const fs::path& root){
    CppAuditOptions options;options.flags={"-I"+(root/"native/include").string(),"-I"+(root/"native/src").string()};
    const auto census=scan_cpp_audit_sources(root,{{"native/src/floorplan_internal.hpp"},{"native/src/floorplan_cross.cpp"},{"native/src/pcb_placement_breathe.cpp"},{"native/src/precision_ops.cpp"},{"native/include/schgen/board_decision_policy.hpp"}},options);
    // Prefix counting also counts the two accounting-wrapper lambdas inside
    // the vector overload. Assert the actual overloads without hiding lambdas.
    require(census.functions.count("native/src/floorplan_cross.cpp::schgen::floorplan_detail::Engine::estimate [double ()]")&&census.functions.count("native/src/floorplan_cross.cpp::schgen::floorplan_detail::Engine::estimate [double (const std::vector<const FloorplanBlock *> &, const std::string &)]"),"both actual Engine::estimate implementations scan without abort");
    require(std::none_of(census.constants.begin(),census.constants.end(),[](const auto& c){return c.symbol=="native/src/floorplan_internal.hpp::schgen::floorplan_detail::Engine::raw_area";}),"actual mutable Engine state is not policy");
    require(std::any_of(census.constants.begin(),census.constants.end(),[](const auto& c){return c.symbol=="native/include/schgen/board_decision_policy.hpp::schgen::board_decision_policy::breathe_epsilon_mm";}),"actual lifted breathe epsilon stays visible at its storage owner");
    NativeLedger none;NativeQuantizations unregistered;const auto report=check_native_audits(census,none,unregistered);
    require(!report.ok&&!report.undeclared.empty()&&!report.unregistered_quantization.empty(),"actual engineering constants and raw precision still fail without truthful policy");
    require(std::all_of(census.quantization.begin(),census.quantization.end(),[](const auto& q){return q.function.find("native/src/precision_ops.cpp::schgen::")==0;}),"all sixteen original raw-site lines are now owned by real scalar precision implementations");
    std::cout<<report.summary()<<'\n';
}
}
int main(int argc,char** argv){try{if(argc>2)throw std::runtime_error("usage: native_cpp_auditor_contracts [repo-root]");source_contracts();if(argc==2)production_contracts(fs::absolute(argv[1]));std::cout<<checks<<" C++ auditor identity/storage contracts passed\n";}catch(const std::exception& e){std::cerr<<"C++ auditor contracts FAILED: "<<e.what()<<'\n';return 1;}}
