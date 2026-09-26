#ifdef SCHGEN_SERIAL_AUDIT_SOURCE
#include SCHGEN_SERIAL_AUDIT_SOURCE
#endif
#include "schgen/native_audit_state.hpp"
#include "schgen/board_policy.hpp"
#include <algorithm>
#include <chrono>
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
    std::vector<CppAuditSource> files{{"native/tests/data/audit_ast_projection/policy.cpp"},{"native/tests/data/audit_ast_projection/policy.hpp"}};
    const auto serial=scan_cpp_audit_sources(root,files,options(root,1));
    require(serial.n_files==2&&!serial.constants.empty()&&!serial.quantization.empty(),"adversarial census must contain real findings");
    NativeLedger ledger;NativeQuantizations quant;
    const auto verdict=check_native_audits(serial,ledger,quant).summary();
    for(std::size_t workers:{2,3,4}){
        const auto parallel=scan_cpp_audit_sources(root,files,options(root,workers));
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
    std::cout<<"parallel audit exact-census, failure and timeout contracts PASS\n";
}
}
int main(int argc,char** argv){try{
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
