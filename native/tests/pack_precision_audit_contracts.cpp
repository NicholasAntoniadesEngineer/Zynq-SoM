#include "schgen/native_audit_state.hpp"
#include "pack_precision_fixture.hpp"
#include <iostream>

int main(int argc,char** argv) { try {
    using namespace schgen;
    if(argc!=2&&argc!=3)throw std::runtime_error("[before-root] after-root");
    const auto scan=[](const char* root,const std::vector<CppAuditSource>& files) {
        CppAuditOptions options;
        options.workers=1;
        options.flags={"-I"+(std::filesystem::path(root)/"native/include").string(),
                       "-I"+(std::filesystem::path(root)/"native/src").string()};
        return scan_cpp_audit_sources(root,files,options);
    };
    const std::set<std::string> consumers{
        "native/src/pack.cpp::schgen::shelf_pack","native/src/pack.cpp::schgen::grid_controls",
        "native/src/pack_edges.cpp::schgen::pack_edges","native/src/pack_edges.cpp::schgen::hf_cap_pose",
        "native/src/pack_edges.cpp::schgen::rounded_run_coordinate"};
    const std::vector<CppAuditSource> files{{"native/src/pack.cpp"},{"native/src/pack_edges.cpp"}};
    // The AST reports a direct raw call and its callee DeclRefExpr separately.
    // Match the audit's public diagnostic identity, not duplicate AST events.
    const auto identities=[](const CppSourceCensus& census,const std::set<std::string>& selected) {
        std::set<std::tuple<std::string,std::string,std::string>> out;
        for(const auto& site:census.quantization)
            if(selected.empty()||selected.count(site.function))
                out.emplace(site.function,site.site,site.detector);
        return out;
    };
    if(argc==3) {
        const auto before=scan(argv[1],files);
        const auto n=identities(before,consumers).size();
        if(n!=14)throw std::runtime_error("pre-extraction fourteen scalar sites changed; actual="+std::to_string(n));
        const auto events=std::count_if(before.quantization.begin(),before.quantization.end(),
            [&](const auto& site){return consumers.count(site.function)!=0;});
        if(events!=27)throw std::runtime_error("expected all 27 original detector events, including duplicates; actual="+std::to_string(events));
    }
    const auto after=scan(argv[argc-1],files);
    for(const auto& site:after.quantization)
        if(consumers.count(site.function))throw std::runtime_error("raw boundary left in consumer: "+site.site);
    const auto scalars=scan(argv[argc-1],{{"native/src/pack_precision.cpp"}});
    NativeQuantizations all,selected;register_native_quantizations(all);
    for(const auto& declaration:all.declarations())
        if(pack_precision_fixture::added(declaration.name))selected.declare(declaration);
    if(selected.declarations().size()!=7 || identities(scalars,{}).size()!=8)
        throw std::runtime_error("seven registrations/eight scalar detector sites required");
    if(scalars.quantization.size()!=15)
        throw std::runtime_error("all 15 scalar detector events, including duplicates, must remain visible");
    NativeLedger no_policy;const auto checked=check_native_audits(scalars,no_policy,selected);
    if(!checked.ok)throw std::runtime_error(checked.summary());
    for(const auto& name:pack_precision_fixture::names) {
        const auto symbol="native/src/pack_precision.cpp::schgen::"+name;
        if(!scalars.functions.count(symbol)||!std::any_of(scalars.quantization.begin(),scalars.quantization.end(),
            [&](const auto& site){return site.function==symbol;}))
            throw std::runtime_error("registered name has no actual scalar boundary: "+name);
    }
    std::cout<<"Pack extraction source census PASS; other pack findings remain visible and out of this batch\n";
    return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}}
