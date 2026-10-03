#include "schgen/native_audit_state.hpp"
#include <atomic>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <thread>
#include <sys/resource.h>
#include <unistd.h>
#ifdef __APPLE__
#include <libproc.h>
#endif
namespace schgen {
CppSourceCensus scan_cpp_audit_sources_reference(const std::filesystem::path&,
    const std::vector<CppAuditSource>&,const CppAuditOptions&);
}
namespace {
using namespace schgen;
std::string encode(const CppSourceCensus& c){
    std::ostringstream out;out<<"files "<<c.n_files<<'\n';
    for(const auto& v:c.constants)out<<"constant "<<std::quoted(v.symbol)<<' '<<std::quoted(v.site)<<' '<<v.buried<<'\n';
    for(const auto& v:c.functions)out<<"function "<<std::quoted(v)<<'\n';
    for(const auto& v:c.quantization)out<<"quantization "<<std::quoted(v.site)<<' '<<std::quoted(v.function)<<' '<<std::quoted(v.detector)<<'\n';
    return out.str();
}
std::uint64_t resident_tree(pid_t pid,unsigned& children){
#ifdef __APPLE__
    proc_taskinfo task{};
    std::uint64_t sum=::proc_pidinfo(pid,PROC_PIDTASKINFO,0,&task,sizeof task)==sizeof task?task.pti_resident_size:0;
    // The benchmark owns at most two compiler trees; cap traversal storage.
    pid_t pids[128]{};const auto count=::proc_listchildpids(pid,pids,sizeof pids);
    if(count>0)for(const auto child:pids)if(child>0&&child!=pid){++children;sum+=resident_tree(child,children);}
    return sum;
#else
    (void)pid;(void)children;return 0;
#endif
}
}
int main(int argc,char** argv){try{
    if(argc<5)throw std::runtime_error("usage: census baseline|pipe ROOT OUTPUT RELATIVE_SOURCE...");
    const std::string mode=argv[1];if(mode!="baseline"&&mode!="pipe")throw std::runtime_error("unknown mode");
    const auto root=std::filesystem::absolute(argv[2]);
    std::vector<CppAuditSource> manifest;for(int i=4;i<argc;++i)manifest.push_back({argv[i]});
    CppAuditOptions options;options.compiler="/usr/bin/clang++";options.workers=2;options.timeout=std::chrono::seconds(120);
    options.flags={"-I"+(root/"native/include").string(),"-I"+(root/"native/src").string()};
    std::atomic<bool> done{false};std::uint64_t aggregate_peak=0;unsigned child_peak=0;
    std::thread sampler([&]{do{unsigned children=0;aggregate_peak=std::max(aggregate_peak,resident_tree(::getpid(),children));child_peak=std::max(child_peak,children);
        std::this_thread::sleep_for(std::chrono::milliseconds(20));}while(!done.load());});
    CppSourceCensus census;const auto start=std::chrono::steady_clock::now();
    try{census=(mode=="baseline"?scan_cpp_audit_sources_reference:scan_cpp_audit_sources)(root,manifest,options);}
    catch(...){done=true;sampler.join();throw;}
    const auto elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();done=true;sampler.join();
    std::ofstream out(argv[3]);out<<encode(census);out.close();if(!out)throw std::runtime_error("write census failed");
    rusage usage{};::getrusage(RUSAGE_SELF,&usage);
    std::cout<<std::setprecision(9)<<"mode="<<mode<<" files="<<manifest.size()<<" workers=2 seconds="<<elapsed
        <<" sampled_aggregate_peak_bytes="<<(child_peak?aggregate_peak:0)<<" observed_child_peak="<<child_peak
        <<" parent_ru_maxrss="<<usage.ru_maxrss<<" constants="<<census.constants.size()<<" functions="<<census.functions.size()
        <<" sites="<<census.quantization.size()<<'\n';
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
