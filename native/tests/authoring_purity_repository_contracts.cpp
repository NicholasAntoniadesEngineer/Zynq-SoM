#include "schgen/authoring_purity_config.hpp"
#include "schgen/authoring_context.hpp"
#include <chrono>
#include <iostream>
#include <stdexcept>
#include <sys/resource.h>

int main(int argc,char** argv) {
    try {
        if (argc!=4) throw std::runtime_error("usage: contracts REPOSITORY CONFIGURATION closure|census");
        const std::string mode=argv[3];
        if (mode!="closure" && mode!="census") throw std::runtime_error("mode must be closure or census");
        const auto start=std::chrono::steady_clock::now();
        const auto result=mode=="census"?schgen::check_native_authoring_purity_census(argv[1],argv[2]):
            schgen::check_native_authoring_purity(argv[1],argv[2],schgen::make_authoring_context(argv[1]));
        std::cout<<result.report();
        rusage usage{};
        std::cerr<<"elapsed_ms="<<std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-start).count();
        if (getrusage(RUSAGE_SELF,&usage)==0) std::cerr<<" maxrss_native_units="<<usage.ru_maxrss;
        std::cerr<<'\n';
        return result.ok()?0:1;
    } catch (const std::exception& error) { std::cerr<<error.what()<<'\n'; return 1; }
}
