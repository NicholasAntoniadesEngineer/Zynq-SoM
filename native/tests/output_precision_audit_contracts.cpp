#include "output_precision_registration.hpp"
#include "output_precision_fixture.hpp"
#include <iostream>

// The private whole-core build instruments occupancy.cpp; source-only audit
// execution has no scalar-entry observation and must not fabricate receipts.
extern "C" void __cyg_profile_func_enter(void*,void*){}
extern "C" void __cyg_profile_func_exit(void*,void*){}
int main(int argc,char** argv){try{
    const bool scalars_only=argc==4&&std::string(argv[3])=="--scalars-only";
    if(argc!=2&&argc!=3&&!scalars_only)throw std::runtime_error("[before-root] after-root [--scalars-only]");
    const char* after_root=argv[scalars_only?2:argc-1];
    using namespace schgen;
    const std::vector<CppAuditSource> consumers{{"native/src/floorplan_svg.cpp"},
        {"native/src/pcb_project.cpp"},{"native/src/pcb_silk.cpp"},
        {"native/src/ratsnest_gate.cpp"},{"native/src/pcb_escape_copper.cpp"},
        {"native/src/pcb_escape_plan.cpp"}};
    auto scan=[&](const char* root,const std::vector<CppAuditSource>& files){
        const auto directory=std::filesystem::absolute(root);
        CppAuditOptions options;
        // Use the existing serial scanner path for this focused proof. The
        // separately retained default-worker ASan run exhausts its worker stack.
        options.workers=1;
        options.flags={"-I"+(directory/"native/include").string(),
            "-I"+(directory/"native/src").string(),"-ffp-contract=off"};
        return scan_cpp_audit_sources(directory,files,options);
    };
    if(!scalars_only){
    if(argc==3){
    const auto before=scan(argv[1],consumers);
    std::cout<<"BEFORE "<<before.n_files<<" files / "<<before.quantization.size()<<" raw sites\n";
    for(const auto& site:before.quantization)std::cout<<site.site<<' '<<site.function<<' '<<site.detector<<'\n';
    if(before.n_files!=6||before.quantization.size()!=40)throw std::runtime_error("original source census differs");
    }
    const auto after=scan(after_root,consumers);
    std::cout<<"AFTER "<<after.n_files<<" files / "<<after.quantization.size()<<" raw sites\n";
    for(const auto& site:after.quantization)std::cout<<site.site<<' '<<site.function<<' '<<site.detector<<'\n';
    if(after.n_files!=6||!after.quantization.empty())throw std::runtime_error("consumer boundary not extracted");
    }
    const auto scalars=scan(after_root,{{"native/src/output_precision.cpp"}});
    NativeLedger no_policy;NativeQuantizations registered;
    NativeQuantizations all;register_native_quantizations(all);
    for(const auto& declaration:all.declarations())
        if(output_precision_fixture::added(declaration.name))registered.declare(declaration);
    const auto checked=check_native_audits(scalars,no_policy,registered);
    std::cout<<"SCALARS "<<scalars.quantization.size()<<" raw sites\n"<<checked.summary()<<'\n';
    // Two checked truncation values add four real detector events (call and
    // callee reference for each); retain the complete duplicate-inclusive census.
    if(!checked.ok||scalars.n_files!=1||scalars.quantization.size()!=40)throw std::runtime_error("scalar audit failed");
    const auto declarations=registered.declarations();
    if(declarations.size()!=19)throw std::runtime_error("unexpected registration cardinality");
    for(const auto& declaration:declarations){
        const auto arity=declaration.name=="floorplan_svg_coordinate_precision1dp"?3u:1u;
        if(declaration.arity!=arity)throw std::runtime_error("incorrect scalar arity: "+declaration.name);
    }
    for(const auto& name:output_precision_fixture::names){
        const auto symbol="native/src/output_precision.cpp::schgen::"+name;
        if(!scalars.functions.count(symbol)||!std::any_of(scalars.quantization.begin(),scalars.quantization.end(),
            [&](const auto& site){return site.function==symbol;}))
            throw std::runtime_error("registration does not own a detected scalar boundary: "+name);
    }
    std::cout<<"All 19 registrations own actual compiler-detected boundaries. Consumer constants remain out of scope.\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
