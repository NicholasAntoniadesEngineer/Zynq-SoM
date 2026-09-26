#include "schgen/native_audit_state.hpp"
#include "placement_precision_fixture.hpp"
#include <iostream>

// A real compiler census, not scanner-derived registration. Parent owns the
// production registry; this test only verifies extraction and named boundaries.
int main(int argc,char** argv){try{
    if(argc!=2&&argc!=3)throw std::runtime_error("[before-root] after-root");
    using namespace schgen;
    std::vector<CppAuditSource> consumers;
    for(const auto* name:{"inputs","pack","variants","zones","moves","model"})
        consumers.push_back({std::string("native/src/pcb_placement_")+name+".cpp"});
    auto scan=[&](const char* root,const std::vector<CppAuditSource>& files){
        CppAuditOptions options;options.workers=1;options.timeout=std::chrono::milliseconds{120000};
        options.flags={"-I"+(std::filesystem::path(root)/"native/include").string(),
            "-I"+(std::filesystem::path(root)/"native/src").string(),"-ffp-contract=off"};
        return scan_cpp_audit_sources(root,files,options);
    };
    if(argc==3){
        const auto before=scan(argv[1],consumers);
        if(before.n_files!=6||before.quantization.empty())throw std::runtime_error("missing pre-change raw census");
        std::cout<<"before: "<<before.quantization.size()<<" findings\n";
        for(const auto& site:before.quantization)std::cout<<site.site<<' '<<site.function<<' '<<site.detector<<'\n';
    }
    const auto after=scan(argv[argc-1],consumers);
    if(after.n_files!=6||!after.quantization.empty())throw std::runtime_error("raw placement consumer boundary remains");
    const auto scalar=scan(argv[argc-1],{{"native/src/placement_precision.cpp"}});
    if(scalar.n_files!=1||!scalar.constants.empty())throw std::runtime_error("scalar census missing or acquired policy storage");
    std::set<std::string> expected;
    for(const auto& name:placement_precision_fixture::names){
        const auto symbol="native/src/placement_precision.cpp::schgen::"+name;expected.insert(symbol);
        if(!scalar.functions.count(symbol)||!std::any_of(scalar.quantization.begin(),scalar.quantization.end(),
            [&](const auto& row){return row.function==symbol;}))throw std::runtime_error("named operation lacks actual scalar boundary: "+name);
    }
    for(const auto& row:scalar.quantization)if(!expected.count(row.function))throw std::runtime_error("unowned scalar math");
    std::cout<<"after: zero raw consumer findings; "<<scalar.quantization.size()<<" findings in 19 real scalar functions\n";
    std::cout<<"Production registry and full-board gate verification remain parent-owned.\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
