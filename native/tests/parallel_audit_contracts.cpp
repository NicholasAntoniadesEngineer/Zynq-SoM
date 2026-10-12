#ifdef SCHGEN_SERIAL_AUDIT_SOURCE
#include SCHGEN_SERIAL_AUDIT_SOURCE
#endif
#include "schgen/native_audit_state.hpp"
#include "schgen/board_policy.hpp"
#include "schgen/process.hpp"
#include "../src/audit_dependencies_internal.hpp"
#include "../src/audit_parallel_internal.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <thread>
#include <unistd.h>

namespace {
using namespace schgen;
std::string census_text(const CppSourceCensus& c){
    std::ostringstream out;out<<"files "<<c.n_files<<'\n';
    for(const auto& x:c.constants)out<<"constant "<<std::quoted(x.symbol)<<' '<<std::quoted(x.site)<<' '<<x.buried<<'\n';
    for(const auto& x:c.functions)out<<"function "<<std::quoted(x)<<'\n';
    for(const auto& x:c.quantization)out<<"site "<<std::quoted(x.site)<<' '<<std::quoted(x.function)<<' '<<std::quoted(x.detector)<<'\n';
    return out.str();
}
void require(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
template<class F> std::string failure(F f){try{f();}catch(const std::exception& e){return e.what();}throw std::runtime_error("expected audit rejection");}
struct Scratch {
    std::filesystem::path path;
    Scratch(){auto s=(std::filesystem::temp_directory_path()/"schgen_parallel_audit_XXXXXX").string();if(!mkdtemp(s.data()))throw std::runtime_error("mkdtemp failed");path=s;}
    ~Scratch(){std::error_code e;std::filesystem::remove_all(path,e);}
};
void write(const std::filesystem::path& path,const std::string& text){std::ofstream out(path);out<<text;out.close();require(bool(out),"cannot write proof file");}
CppAuditOptions options(const std::filesystem::path& root,std::size_t workers){CppAuditOptions o;o.workers=workers;o.flags={"-I"+(root/"native/include").string(),"-I"+(root/"native/src").string()};return o;}
void contracts(const std::filesystem::path& root,const std::string& self){
    for(std::size_t workers:{1,2,3,4}) {
        std::atomic<std::size_t> live{0},peak{0};std::vector<int> visited(13);
        audit_detail::for_each_input(visited.size(),workers,[&](std::size_t i){
            const auto n=live.fetch_add(1)+1;auto maximum=peak.load();
            while(n>maximum&&!peak.compare_exchange_weak(maximum,n)){}
            ++visited[i];std::this_thread::yield();live.fetch_sub(1);
        });
        require(live==0&&peak<=workers,"audit phase exceeded worker bound or returned before joining");
        require(std::all_of(visited.begin(),visited.end(),[](int n){return n==1;}),"audit phase skipped or repeated an input");
        audit_detail::for_each_input(0,workers,[](std::size_t){throw std::runtime_error("empty phase executed work");});
    }
    for(std::size_t workers:{2,3,4}) {
        std::atomic<bool> later_failed{false};std::atomic<int> live{0};
        const auto message=failure([&]{audit_detail::for_each_input(9,workers,[&](std::size_t i){
            struct Active {std::atomic<int>& n;Active(std::atomic<int>& x):n(x){++n;}~Active(){--n;}} active(live);
            if(i==0){
                const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(5);
                while(!later_failed&&std::chrono::steady_clock::now()<deadline)std::this_thread::yield();
                require(later_failed,"independent audit worker did not advance");
                throw std::runtime_error("earliest input");
            }
            if(i==1){later_failed=true;throw std::runtime_error("fast later input");}
        });});
        require(message=="earliest input"&&live==0,"audit phase lost failure ordering or failed to join");
    }
    for(std::size_t workers:{0,5})failure([&]{audit_detail::for_each_input(1,workers,[](std::size_t){});});
    const auto parsed=audit_detail::dependency_paths("schgen_audit_deps: source.cpp \\" "\n"
        " folder\\ name/\\#policy$$.hpp\n");
    require(parsed.size()==2,"dependency continuation added a spurious path");
    require(parsed.count(std::filesystem::absolute("folder name/#policy$.hpp")),"Make dependency escaping lost filename identity");
    for(const auto* newline:{"\n","\r\n"}) {
        const auto continued=audit_detail::dependency_paths(std::string("schgen_audit_deps: one.cpp\\")+newline+"two.hpp\n");
        require(continued.size()==2&&continued.count(std::filesystem::absolute("one.cpp"))&&
                continued.count(std::filesystem::absolute("two.hpp")),"Make continuation must separate adjacent tokens");
    }
    for(const auto* bad:{"wrong: file.cpp\n","schgen_audit_deps:","schgen_audit_deps: $(unsafe)",
                         "schgen_audit_deps: bad\\path.hpp","schgen_audit_deps: truncated\\"})
        failure([&]{audit_detail::dependency_paths(bad);});
    std::vector<CppAuditSource> files{{"native/tests/data/audit_ast_projection/policy.cpp"},{"native/tests/data/audit_ast_projection/policy.hpp"}};
    const auto serial=scan_cpp_audit_sources(root,files,options(root,1));
    require(serial.n_files==2&&!serial.constants.empty()&&!serial.quantization.empty(),"adversarial census must contain real findings");
    NativeLedger ledger;NativeQuantizations quant;
    const auto verdict=check_native_audits(serial,ledger,quant).summary();
    for(std::size_t workers:{2,3,4}){
        auto configured=options(root,workers);std::vector<CppAuditTiming> timings;
        configured.timings=&timings;
        const auto parallel=scan_cpp_audit_sources(root,files,configured);
        require(timings.size()==files.size(),"successful diagnostics cover every manifest source");
        for(std::size_t i=0;i<timings.size();++i){const auto& t=timings[i];
            require(t.source==files[i].path,"diagnostic publication preserves manifest order");
            for(const auto value:{t.dependency_seconds,t.snapshot_seconds,t.ast_seconds,t.visitor_seconds,t.preprocessing_seconds,t.final_dependency_seconds,t.first_byte_seconds,t.projection_wait_seconds,t.parsing_seconds})
                require(std::isfinite(value)&&value>=0,"phase elapsed time must be finite and nonnegative");
            require(t.first_byte_seconds+t.projection_wait_seconds+t.parsing_seconds<=t.ast_seconds+1e-6,"AST subphases belong within overall phase");
        }
        const auto saved=timings.front().source;
        failure([&]{scan_cpp_audit_sources(root,{{"missing.cpp"}},configured);});
        require(timings.size()==files.size()&&timings.front().source==saved,"failure cannot publish partial timings");
        require(census_text(serial)==census_text(parallel),"exact ordered census and duplicate populations differ");
        require(check_native_audits(parallel,ledger,quant).summary()==verdict,"gate findings differ");
    }
    std::reverse(files.begin(),files.end());
    require(census_text(scan_cpp_audit_sources(root,files,options(root,1)))==census_text(scan_cpp_audit_sources(root,files,options(root,2))),"reversed manifest order was not preserved");
    for(std::size_t workers:{0,5})failure([&]{scan_cpp_audit_sources(root,files,options(root,workers));});
    auto duplicate=files;duplicate.push_back(files.front());failure([&]{scan_cpp_audit_sources(root,duplicate,options(root,2));});
    failure([&]{scan_cpp_audit_sources(root,{{"../escape.cpp"}},options(root,2));});
    failure([&]{scan_cpp_audit_sources(root,{{"missing.cpp"}},options(root,2));});
    failure([&]{scan_cpp_audit_sources(root,{},options(root,2));});
    Scratch scratch;
    // A compiler-level rendezvous, not just a helper test: both final -M
    // requests must run concurrently after their own macro passes finish.
    for(std::size_t workers:{2,3,4}) {
        for(const auto* name:{"left","right"}) {
            write(scratch.path/(std::string(name)+".cpp"),"");
            std::filesystem::remove(scratch.path/(std::string(name)+".macro_done"));
            std::filesystem::remove(scratch.path/(std::string(name)+".final_started"));
        }
        auto wave=options(root,workers);wave.compiler=self;wave.flags={"--final-graph-compiler"};
        require(scan_cpp_audit_sources(scratch.path,{{"left.cpp"},{"right.cpp"}},wave).n_files==2,
                "final compiler dependency phase did not complete its bounded parallel wave");
    }
    std::vector<CppAuditSource> batches;
    for(int i=0;i<5;++i){
        const auto name="unit"+std::to_string(i)+".cpp";batches.push_back({name});
        write(scratch.path/name,"#define GAP 0.125\nconstexpr double margin=0.25;\ndouble snap(double x){return __builtin_floor(x);}\n");
    }
    const auto ordered=scan_cpp_audit_sources(scratch.path,batches,options(root,1));
    require(ordered.n_files==5&&ordered.constants.size()==10&&!ordered.quantization.empty(),"multi-batch fixture must include AST and macro findings");
    for(std::size_t workers:{2,3,4})
        require(census_text(ordered)==census_text(scan_cpp_audit_sources(scratch.path,batches,options(root,workers))),"partial final batch or macro order differs");
    write(scratch.path/"first.cpp","first syntax error\n");write(scratch.path/"second.cpp","second syntax error\n");
    const std::vector<CppAuditSource> bad{{"first.cpp"},{"second.cpp"}};
    const auto first=failure([&]{scan_cpp_audit_sources(scratch.path,bad,options(root,1));});
    require(first==failure([&]{scan_cpp_audit_sources(scratch.path,bad,options(root,2));}),"compiler errors are not selected in manifest order");
    auto absent=options(root,2);absent.compiler="/nonexistent/compiler";failure([&]{scan_cpp_audit_sources(scratch.path,bad,absent);});
    auto slow=options(root,2);slow.compiler=self;slow.flags={"--slow-compiler"};slow.timeout=std::chrono::milliseconds{25};
    const auto message=failure([&]{scan_cpp_audit_sources(scratch.path,bad,slow);});
    require(message.find("timed out")!=std::string::npos,"worker timeout must propagate, never yield a partial census");
    for(const auto* phase:{"ast","preprocessor","earlier","queued"})for(std::size_t workers:{1,2}){
        for(const auto& file:bad)write(scratch.path/file.path,"constexpr double stable=0.25;\n");
        auto changing=options(root,workers);changing.compiler=self;changing.flags={"--mutating-compiler",phase};
        const auto changed=failure([&]{scan_cpp_audit_sources(scratch.path,bad,changing);});
        require(changed.find("source changed during audit")!=std::string::npos,
                "concurrently edited source must not publish a mixed-version census");
    }
    for(const auto* phase:{"ast","preprocessor","appearing","appearing_earlier"})for(std::size_t workers:{1,2}) {
        std::filesystem::create_directories(scratch.path/"nested path");
        write(scratch.path/"nested path/#policy$.hpp","#define HEADER_VALUE 0.25\n");
        write(scratch.path/"unlisted.hpp","#include \"nested path/#policy$.hpp\"\n");
        std::error_code ignored;std::filesystem::remove(scratch.path/"appears.hpp",ignored);
        std::filesystem::remove(scratch.path/"first.preprocessed",ignored);
        for(const auto& file:bad) {
            const std::string lookup=(std::string(phase)=="appearing_earlier"&&file.path=="second.cpp")?"":
                "#if __has_include(\"appears.hpp\")\n#include \"appears.hpp\"\n#endif\n";
            write(scratch.path/file.path,"#include \"unlisted.hpp\"\n"+lookup+"constexpr double stable=HEADER_VALUE;\n");
        }
        auto changing=options(root,workers);changing.compiler=self;changing.flags={"--header-mutating-compiler",phase};
        const auto changed=failure([&]{scan_cpp_audit_sources(scratch.path,bad,changing);});
        require(changed.find("dependency changed during audit")!=std::string::npos||
                changed.find("dependency graph changed during audit")!=std::string::npos,
                "transitive or newly appearing include must not publish a mixed-input census");
    }
    std::cout<<"parallel audit exact-census, failure and timeout contracts PASS\n";
}
}
int main(int argc,char** argv){try{
    if(argc>2&&std::string(argv[1])=="--final-graph-compiler") {
        const auto has=[&](const char* flag){return std::find_if(argv+2,argv+argc,[&](const char* a){return std::string(a)==flag;})!=argv+argc;};
        const std::filesystem::path source=argv[argc-1];const auto dir=source.parent_path();
        const auto name=source.stem().string();const auto record="schgen_audit_deps: "+source.string()+"\n";
        if(has("-M")) {
            if(std::filesystem::exists(dir/(name+".macro_done"))) {
                write(dir/(name+".final_started"),"");
                const auto other=dir/((name=="left"?std::string("right"):std::string("left"))+".final_started");
                const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(5);
                while(!std::filesystem::exists(other)&&std::chrono::steady_clock::now()<deadline)
                    std::this_thread::sleep_for(std::chrono::milliseconds(5));
                require(std::filesystem::exists(other),"final dependency revalidation was serialized");
            }
            std::cout<<record;return 0;
        }
        if(has("-E")) {
            for(int i=2;i+1<argc;++i)if(std::string(argv[i])=="-MF")write(argv[i+1],record);
            write(dir/(name+".macro_done"),"");return 0;
        }
        std::cout<<"{\"kind\":\"TranslationUnitDecl\",\"inner\":[]}\n";return 0;
    }
    if(argc>3&&std::string(argv[1])=="--header-mutating-compiler") {
        const auto has=[&](const char* option){return std::find_if(argv+3,argv+argc,[&](const char* a){return std::string(a)==option;})!=argv+argc;};
        const bool dependency=has("-M"),preprocess=has("-E");
        const std::string phase=argv[2];const std::filesystem::path source=argv[argc-1];
        if(source.filename()=="first.cpp"&&!dependency&&((phase=="ast"&&!preprocess)||(phase=="preprocessor"&&preprocess)))
            write(source.parent_path()/"nested path/#policy$.hpp","#define HEADER_VALUE 0.75\n");
        if(phase=="appearing"&&source.filename()=="first.cpp"&&!dependency&&!preprocess)
            write(source.parent_path()/"appears.hpp","constexpr double introduced=0.5;\n");
        if(phase=="appearing_earlier"&&!dependency&&!preprocess&&source.filename()=="second.cpp") {
            // Establish ordering explicitly; worker scheduling must not decide
            // whether this fixture actually edits a previously scanned graph.
            const auto ready=source.parent_path()/"first.preprocessed";
            const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(5);
            while(!std::filesystem::exists(ready)&&std::chrono::steady_clock::now()<deadline)
                std::this_thread::sleep_for(std::chrono::milliseconds(5));
            require(std::filesystem::exists(ready),"first TU preprocessing did not complete");
            write(source.parent_path()/"appears.hpp","constexpr double introduced=0.5;\n");
        }
        std::vector<std::string> command{"clang++"};command.insert(command.end(),argv+3,argv+argc);
        const auto result=run_process(command);
        if(result.exit_code==0&&phase=="appearing_earlier"&&preprocess&&source.filename()=="first.cpp")
            write(source.parent_path()/"first.preprocessed","");
        std::cout<<result.stdout_text;std::cerr<<result.stderr_text;return result.exit_code;
    }
    if(argc>3&&std::string(argv[1])=="--mutating-compiler"){
        const bool preprocess=std::find_if(argv+3,argv+argc,[](const char* arg){return std::string(arg)=="-E";})!=argv+argc;
        const bool dependency=std::find_if(argv+3,argv+argc,[](const char* arg){return std::string(arg)=="-M";})!=argv+argc;
        const std::string phase=argv[2];const std::filesystem::path source=argv[argc-1];
        if(dependency){std::cout<<"schgen_audit_deps: "<<source.string()<<'\n';return 0;}
        if((phase=="ast"&&!preprocess)||(phase=="preprocessor"&&preprocess))
            write(argv[argc-1],"constexpr double changed=0.5;\n");
        if(preprocess&&phase=="earlier"&&source.filename()=="second.cpp")
            write(source.parent_path()/"first.cpp","constexpr double changed=0.5;\n");
        if(preprocess&&phase=="queued"&&source.filename()=="first.cpp")
            write(source.parent_path()/"second.cpp","constexpr double changed=0.5;\n");
        if(!preprocess)std::cout<<"{\"kind\":\"TranslationUnitDecl\",\"inner\":[]}\n";
        else for(int i=3;i+1<argc;++i)if(std::string(argv[i])=="-MF")write(argv[i+1],"schgen_audit_deps: "+source.string()+"\n");
        return 0;
    }
    if(argc>1&&std::string(argv[1])=="--slow-compiler"){std::this_thread::sleep_for(std::chrono::seconds{5});return 0;}
    if(argc==5&&std::string(argv[1])=="--full"){
        const auto root=std::filesystem::absolute(argv[2]);const auto workers=std::stoul(argv[3]);
        const auto begin=std::chrono::steady_clock::now();
        const auto result=scan_cpp_audit_sources(root,native_board_policy_audit_sources(),options(root,workers));
        write(argv[4],census_text(result));
        std::cout<<"workers="<<workers<<" files="<<result.n_files<<" seconds="<<std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count()<<'\n';return 0;
    }
    if(argc!=2)throw std::runtime_error("usage: ROOT | --full ROOT WORKERS OUTPUT");
    contracts(std::filesystem::absolute(argv[1]),std::filesystem::absolute(argv[0]).string());return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
