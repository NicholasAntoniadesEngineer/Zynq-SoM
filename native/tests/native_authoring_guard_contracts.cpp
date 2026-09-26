#include "schgen/native_authoring_guard.hpp"
#include "schgen/authoring_context.hpp"
#include "schgen/example_devkit_authoring.hpp"
#include "schgen/project.hpp"
#include <iostream>
#include <stdexcept>
#include <unistd.h>

namespace {
using namespace schgen;
namespace fs=std::filesystem;
std::size_t checks=0;
void require(bool condition,const std::string& why) { ++checks;if(!condition)throw std::runtime_error(why); }
template<class F>std::string rejects(F fn) {
    try { fn(); }
    catch(const ProjectError& error) { ++checks;return error.what(); }
    throw std::runtime_error("native authoring guard did not fail closed");
}
bool has(const AuthoringPurityResult& result,const std::string& code) {
    for(const auto& finding:result.findings)if(finding.code==code)return true;
    return false;
}
struct Scratch {
    fs::path path;
    Scratch() { auto value=(fs::canonical(fs::temp_directory_path())/"schgen-authoring-guard-XXXXXX").string();
        const auto* created=::mkdtemp(value.data());require(created!=nullptr,"private scratch");path=created; }
    ~Scratch() { std::error_code ignored;fs::remove_all(path,ignored); }
};
void failures(const fs::path& root) {
    Scratch scratch;
    const auto missing=scratch.path/"missing-toolchain.json";
    require(native_authoring_configuration(missing)==missing,"explicit configuration takes precedence");
    const auto native=make_authoring_context(root);
    if(native_authoring_configuration().empty()) {
        const auto unconfigured=rejects([&] {make_guarded_native_authoring_context(root);});
        require(unconfigured.find("incomplete-evidence")!=unconfigured.npos,"unconfigured binary must not search CWD or accept");
    }
    std::size_t reports=0;bool constructor_entered=false;
    const auto message=rejects([&] {
        const auto context=make_guarded_native_authoring_context(root,missing,[&](const auto& result) {
            ++reports;require(!result.ok() && result.native_context_verified,"actual context checked before missing evidence");
            require(has(result,"incomplete-evidence"),"missing evidence classified");
            require(!constructor_entered,"report precedes constructor entry");
        });
        constructor_entered=true;
        (void)author_example_devkit(context);
    });
    require(reports==1 && !constructor_entered,"one report and zero constructor calls on missing config");
    require(message.find("incomplete-evidence")!=message.npos,"full failure report preserved");
    require(!fs::exists(missing) && fs::is_empty(scratch.path),"failed guard publishes no evidence/output files");

    auto invalid=native;bool callback_called=false;
    invalid.part=[&](const std::string&) { callback_called=true;throw std::runtime_error("must not invoke");return CatalogPart{}; };
    reports=0;
    const auto invalid_message=rejects([&] {
        require_native_authoring_guard(root,invalid,missing,[&](const auto& result) {
            ++reports;require(has(result,"unverified-context") && !result.native_context_verified,"foreign target not accepted as metadata");
        });
    });
    require(reports==1 && !callback_called,"unknown callback never executed");
    require(invalid_message.find("unverified-context")!=invalid_message.npos,"context rejection report preserved");
    // An observer repairing the context cannot turn the already failed evidence
    // into acceptance; success/failure belongs to the real check, not callback.
    reports=0;
    rejects([&] {require_native_authoring_guard(root,invalid,missing,[&](const auto&) {++reports;invalid=native;});});
    require(reports==1,"observer repair does not waive original failure");
    reports=0;
    rejects([&] {require_native_authoring_guard(root,native,missing,[&](const auto&) {++reports;});});
    require(reports==1,"repeated invocation does not reuse cached verdict");
    bool observer_threw=false;
    try {require_native_authoring_guard(root,native,missing,[](const auto&) {throw std::runtime_error("observer-error");});}
    catch(const std::runtime_error& error) {observer_threw=std::string(error.what())=="observer-error";}
    require(observer_threw,"observer exception aborts construction");
    require(fs::is_empty(scratch.path),"all failure probes leave output untouched");
}
void live(const fs::path& root,const fs::path& configuration) {
    // Expensive real closure is deliberately opt-in, not repeated per sheet or
    // ordinary offline contract. No supplied checker or fake PASS is available.
    std::size_t reports=0;
    const auto context=make_guarded_native_authoring_context(root,configuration,[&](const auto& result) {
        ++reports;require(result.ok() && result.native_context_verified,"actual native configured closure");
        require(result.parsed_units>0 && result.checked_bodies>0,"real compiler evidence");
    });
    require(reports==1,"one scan/report for four-sheet constructor batch");
    require_native_authoring_context(context);
    require(open_part_catalog((root/"native/catalog.bin").string()),"open live catalog after precondition");
    const auto sheets=author_example_devkit(context);
    require(sheets.size()==4,"checked context produces all four live sheets");
    close_part_catalog();
    // A new real check must reject an observer that replaces the very context
    // the caller planned to use. Native identity is checked again after report.
    auto replaced=make_authoring_context(root);
    bool foreign_called=false;
    const auto why=rejects([&] {require_native_authoring_guard(root,replaced,configuration,[&](const auto& result) {
        require(result.ok(),"real closure before malicious observer mutation");
        replaced.pins=[&](const std::string&)->std::optional<std::set<std::string>> {foreign_called=true;return std::nullopt;};
    });});
    require(why.find("changed during reporting")!=why.npos && !foreign_called,"post-report exact context mutation rejected");
}
} // namespace
int main(int argc,char** argv) {
    try {
        require(argc==2 || argc==4,"usage: contracts REPOSITORY [--live CONFIGURATION]");
        const auto root=fs::canonical(argv[1]);failures(root);
        if(argc==4) {require(std::string(argv[2])=="--live","only --live enables compiler closure");live(root,argv[3]);}
        std::cout<<checks<<" native authoring guard contracts PASS"<<(argc==4?"; actual configured closure and observer mutation":"; fail-closed offline paths")<<'\n';
    } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
}
