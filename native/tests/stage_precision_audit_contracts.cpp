#include "schgen/native_audit_state.hpp"
#include "stage_precision_registration.hpp"
#include "stage_precision_fixture.hpp"
#include <iostream>

int main(int argc,char** argv) { try {
    if(argc!=2&&argc!=3) throw std::runtime_error("[before-root] after-root");
    using namespace schgen;
    const std::vector<CppAuditSource> consumers{{"native/src/pcb_stage_geometry.cpp"},
        {"native/src/pcb_stage_search.cpp"},{"native/src/pcb_stage_power.cpp"},
        {"native/src/pcb_stage_zone.cpp"},{"native/src/pcb_stage_internal.hpp"}};
    auto scan=[&](const char* root,const std::vector<CppAuditSource>& sources){
        CppAuditOptions options;
        options.flags={"-I"+(std::filesystem::path(root)/"native/include").string(),
            "-I"+(std::filesystem::path(root)/"native/src").string(),"-ffp-contract=off"};
        return scan_cpp_audit_sources(root,sources,options);
    };
    if(argc==3){
        const auto before=scan(argv[1],consumers);
        std::cout<<"BEFORE "<<before.n_files<<" files / "<<before.quantization.size()<<" raw sites\n";
        for(const auto& site:before.quantization)std::cout<<site.site<<" "<<site.function<<" "<<site.detector<<'\n';
        if(before.n_files!=5||before.quantization.size()!=68)
            throw std::runtime_error("frozen independent pre-change source census differs");
    }
    const auto after=scan(argv[argc-1],consumers);
    std::cout<<"AFTER CONSUMERS "<<after.n_files<<" files / "<<after.quantization.size()<<" raw sites\n";
    if(after.n_files!=5||!after.quantization.empty())
        throw std::runtime_error("consumer raw sites not fully extracted");
    const auto scalars=scan(argv[argc-1],{{"native/src/stage_precision.cpp"}});
    NativeLedger no_policy;NativeQuantizations registered;
    stage_precision_fixture::register_operations(registered);
    const auto checked=check_native_audits(scalars,no_policy,registered);
    std::cout<<"AFTER SCALARS "<<scalars.quantization.size()<<" sites\n"<<checked.summary()<<'\n';
    for(const auto& site:scalars.quantization)std::cout<<site.site<<" "<<site.function<<" "<<site.detector<<'\n';
    if(!checked.ok||scalars.n_files!=1||scalars.quantization.size()!=36)
        throw std::runtime_error("scalar source census failed or differs from independent exact fixture");
    for(const auto& name:stage_precision_fixture::names){
        const auto symbol="native/src/stage_precision.cpp::schgen::"+name;
        if(!scalars.functions.count(symbol)||!std::any_of(scalars.quantization.begin(),scalars.quantization.end(),
            [&](const auto& site){return site.function==symbol;}))
            throw std::runtime_error("registration has no actual raw scalar boundary: "+name);
    }
    std::cout<<"All 17 registrations own actual compiler-detected boundaries. Consumer policy findings remain out of scope.\n";
    return 0;
} catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;} }
