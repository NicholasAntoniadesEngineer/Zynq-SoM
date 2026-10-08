#include "schgen/native_audit_state.hpp"
#include <algorithm>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <thread>

namespace schgen {
CppSourceCensus scan_cpp_audit_sources_reference(const std::filesystem::path&,
    const std::vector<CppAuditSource>&,const CppAuditOptions&);
}
namespace {
using namespace schgen;
namespace fs=std::filesystem;
void need(bool ok,const std::string& why){if(!ok)throw std::runtime_error(why);}
void put(const fs::path& p,const std::string& s){std::ofstream out(p,std::ios::binary);out<<s;need(bool(out),"fixture write failed");}
std::string read(const fs::path& p){std::ifstream in(p,std::ios::binary);need(bool(in),"fixture read failed");return {std::istreambuf_iterator<char>(in),{}};}
std::string encode(const CppSourceCensus& c){
    std::ostringstream s;s<<c.n_files<<'\n';
    for(const auto& v:c.constants)s<<"C "<<std::quoted(v.symbol)<<' '<<std::quoted(v.site)<<' '<<v.buried<<'\n';
    for(const auto& v:c.functions)s<<"F "<<std::quoted(v)<<'\n';
    for(const auto& v:c.quantization)s<<"Q "<<std::quoted(v.site)<<' '<<std::quoted(v.function)<<' '<<std::quoted(v.detector)<<'\n';
    return s.str();
}
template<class F>std::string error(F f){try{f();}catch(const std::exception& e){return e.what();}throw std::runtime_error("expected propagated failure");}
using Scan=CppSourceCensus(*)(const fs::path&,const std::vector<CppAuditSource>&,const CppAuditOptions&);
void parity(const fs::path& root,const std::vector<CppAuditSource>& manifest,CppAuditOptions options){
    options.workers=1;const auto expected=encode(scan_cpp_audit_sources_reference(root,manifest,options));
    for(const auto scan:{Scan(scan_cpp_audit_sources_reference),Scan(scan_cpp_audit_sources)})
        for(const auto workers:{std::size_t(1),std::size_t(2)}){
            options.workers=workers;need(encode(scan(root,manifest,options))==expected,"exact census/order differs");
        }
}
// Child compiler simulator: no production hook or detector exemption. Used only
// for source-offset boundaries, deterministic queue liveness and failure paths.
int compiler(int argc,char** argv){
    const fs::path file=argv[argc-1];const auto root=file.parent_path();
    const auto name=file.stem().string();const auto contents=read(file);
    bool ast=false;for(int i=1;i<argc;++i)ast|=std::string(argv[i])=="-ast-dump=json";
    if(name=="queuefail_first"||name=="queuefail_second"){
        std::cerr<<"deliberate queue failure "<<name<<'\n';return 15;
    }
    if(name=="unneeded")put(root/"unneeded.started","");
    if(name=="timeout"){std::this_thread::sleep_for(std::chrono::seconds(2));return 0;}
    if(name=="badast"&&ast){std::cout<<"{broken";return 0;}
    if(name=="badpre"&&!ast){std::cerr<<"deliberate preprocessor failure\n";return 12;}
    if(contents=="queue"){
        const auto active=root/(name+(ast?".ast.active":".pre.active"));put(active,"");
        std::size_t count=0;for(const auto& e:fs::directory_iterator(root))if(e.path().extension()==".active")++count;
        if(count>2){std::cerr<<"worker bound exceeded\n";return 13;}
        if(name=="third"&&ast)put(root/"third.started","");
        if(name=="slow"&&ast){
            bool ready=false;for(int i=0;i<500;++i){if(fs::exists(root/"third.started")){ready=true;break;}std::this_thread::sleep_for(std::chrono::milliseconds(10));}
            if(!ready){fs::remove(active);std::cerr<<"fixed batch barrier prevented third TU\n";return 14;}
        }
        fs::remove(active);
    }
    if(!ast){std::cout<<"# 1 "<<std::quoted(file.string())<<"\n#define POLICY 7\n";return 0;}
    std::cout<<"{\"kind\":\"TranslationUnitDecl\",\"inner\":[{\"kind\":\"FunctionDecl\",\"name\":"<<std::quoted(name)
        <<",\"type\":{\"qualType\":\"double (double)\"},\"loc\":{\"file\":"<<std::quoted(file.string())<<",\"offset\":0},\"inner\":[{\"kind\":\"CompoundStmt\",\"inner\":[";
    std::vector<std::size_t> offsets{0};
    for(std::size_t i=0;i<contents.size();++i)if(contents[i]=='\n'){offsets.push_back(i);offsets.push_back(i+1);}
    offsets.push_back(contents.size());if(name=="invalid")offsets.push_back(contents.size()+1);
    for(std::size_t i=0;i<offsets.size();++i){if(i)std::cout<<',';std::cout<<"{\"kind\":\"ImplicitCastExpr\",\"castKind\":\"FloatingToIntegral\",\"range\":{\"begin\":{\"offset\":"<<offsets[i]<<"}}}";}
    std::cout<<"]}]}]}";return 0;
}
}
int main(int argc,char** argv){try{
    if(argc>1&&std::string(argv[1]).rfind('-',0)==0)return compiler(argc,argv);
    need(argc==2,"scratch parent required");
    const auto root=fs::absolute(fs::path(argv[1])/std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
    need(fs::create_directories(root),"fresh scratch required");
    CppAuditOptions real;real.timeout=std::chrono::seconds(30);
    put(root/"one.cpp","#define PITCH 3.5\nnamespace p { constexpr double gap=1.25; double f(double x){return __builtin_round(x)+gap;} }\n");
    put(root/"two.cpp","namespace p { double f(double x){return int(x);}\n int f(int x){return x;}\n double g(double x){return [x]{return __builtin_floor(x);}();} }\n");
    put(root/"three.hpp","namespace p { struct B {static constexpr double margin=2.;}; }\n");
    std::vector<CppAuditSource> manifest{{"two.cpp"},{"one.cpp"},{"three.hpp"}};
    parity(root,manifest,real);
    NativeLedger ledger;NativeQuantizations registry;
    const auto before=scan_cpp_audit_sources_reference(root,manifest,real);
    for(const auto& mutation:{std::string("namespace p { double hidden(double gap){return gap-0.05;} }\n"),
                             std::string("namespace p { double hidden(double x){constexpr double SECRET=4.2;return x+SECRET;} }\n")}){
        put(root/"mutation.cpp",mutation);auto changed=manifest;changed.push_back({"mutation.cpp"});parity(root,changed,real);
        real.workers=2;const auto after=scan_cpp_audit_sources(root,changed,real);
        need(encode(before)!=encode(after),"source mutation disappeared");
        need(check_native_audits(after,ledger,registry).summary()==check_native_audits(scan_cpp_audit_sources_reference(root,changed,real),ledger,registry).summary(),"mutation verdict differs");
    }
    put(root/"first_bad.cpp","double first( {\n");put(root/"second_bad.cpp","double second( {\n");
    const std::vector<CppAuditSource> broken{{"one.cpp"},{"first_bad.cpp"},{"second_bad.cpp"}};
    real.workers=1;const auto expected_error=error([&]{scan_cpp_audit_sources_reference(root,broken,real);});
    for(const auto workers:{std::size_t(1),std::size_t(2)}){real.workers=workers;need(error([&]{scan_cpp_audit_sources(root,broken,real);})==expected_error,"manifest-priority diagnostic differs");}
    CppAuditOptions fake;fake.compiler=fs::absolute(argv[0]).string();fake.timeout=std::chrono::seconds(10);
    for(const auto& contents:{std::string(""),std::string("x"),std::string("\n"),std::string("a\r\nb\nlast"),std::string(4096,'\n')}){
        put(root/"lines.cpp",contents);parity(root,{{"lines.cpp"}},fake);
        const auto census=scan_cpp_audit_sources(root,{{"lines.cpp"}},fake);
        std::vector<std::size_t> offsets{0};for(std::size_t i=0;i<contents.size();++i)if(contents[i]=='\n'){offsets.push_back(i);offsets.push_back(i+1);}offsets.push_back(contents.size());
        need(census.quantization.size()==offsets.size(),"lost source-offset events");
        for(std::size_t i=0;i<offsets.size();++i){const auto expected=std::count(contents.begin(),contents.begin()+static_cast<std::ptrdiff_t>(offsets[i]),'\n')+1;
            need(census.quantization[i].site=="lines.cpp:"+std::to_string(expected),"independent half-open newline oracle differs");}
    }
    for(const auto* name:{"invalid","badast","badpre"}){
        put(root/(std::string(name)+".cpp"),"a\nb");std::vector<CppAuditSource> bad{{"one.cpp"},{std::string(name)+".cpp"}};
        fake.workers=1;const auto diagnostic=error([&]{scan_cpp_audit_sources_reference(root,bad,fake);});
        fake.workers=2;need(error([&]{scan_cpp_audit_sources(root,bad,fake);})==diagnostic,"parser/preprocessor/offset error differs");
    }
    fake.workers=2;
    for(const auto& bad:{std::vector<CppAuditSource>{},std::vector<CppAuditSource>{{"absent.cpp"}},std::vector<CppAuditSource>{{"one.cpp"},{"one.cpp"}},std::vector<CppAuditSource>{{"../escape.cpp"}}})
        need(error([&]{scan_cpp_audit_sources(root,bad,fake);})==error([&]{scan_cpp_audit_sources_reference(root,bad,fake);}),"manifest validation changed");
    put(root/"timeout.cpp","");fake.timeout=std::chrono::milliseconds(100);
    (void)error([&]{scan_cpp_audit_sources(root,{{"one.cpp"},{"timeout.cpp"}},fake);});
    fake.timeout=std::chrono::seconds(10);
    for(const auto* name:{"queuefail_first","queuefail_second","unneeded"})put(root/(std::string(name)+".cpp"),"");
    const std::vector<CppAuditSource> fail_fast{{"queuefail_first.cpp"},{"queuefail_second.cpp"},{"unneeded.cpp"}};
    const auto old_failure=error([&]{scan_cpp_audit_sources_reference(root,fail_fast,fake);});
    // The frozen batch implementation also stops between failed batches. Use
    // the current implementation's observable launch marker to require no
    // suffix work, without depending on the relative timing of two failures.
    fs::remove(root/"unneeded.started");
    need(error([&]{scan_cpp_audit_sources(root,fail_fast,fake);})==old_failure,"fail-fast changed earliest manifest failure");
    need(!fs::exists(root/"unneeded.started"),"compiler suffix launched after a decisive failure");
    for(const auto* name:{"slow","fast","third"})put(root/(std::string(name)+".cpp"),"queue");
    const std::vector<CppAuditSource> queued{{"slow.cpp"},{"fast.cpp"},{"third.cpp"}};
    need(error([&]{scan_cpp_audit_sources_reference(root,queued,fake);}).find("fixed batch barrier")!=std::string::npos,"liveness test did not reject old batch scheduler");
    // Old scheduler cannot reach third; no third marker should exist.
    need(!fs::exists(root/"third.started"),"unexpected baseline scheduling");
    const auto queued_census=scan_cpp_audit_sources(root,queued,fake);
    need(queued_census.n_files==3&&fs::exists(root/"third.started"),"idle worker did not take third TU");
    fake.workers=1;need(encode(queued_census)==encode(scan_cpp_audit_sources_reference(root,queued,fake)),"out-of-order completion changed manifest census order");
    for(const auto& e:fs::directory_iterator(root))need(e.path().extension()!=".active","unjoined simulated compiler");
    std::cout<<"PASS exact original/candidate serial/two-worker censuses and diagnostics; real compiler mutations; newline boundaries; malformed AST/preprocess/timeout/manifest failures; bounded queue liveness kills old scheduler\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
