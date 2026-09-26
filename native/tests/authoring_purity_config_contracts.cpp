#include "schgen/authoring_purity_config.hpp"
#include "schgen/authoring.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <unistd.h>

namespace {
namespace fs=std::filesystem;
std::size_t checks=0;
void require(bool ok,const std::string& why) { ++checks; if (!ok) throw std::runtime_error(why); }
std::string quote(const std::string& s) {
    std::string out="\"";
    for (const char c:s) { if (c=='\\' || c=='"') out+='\\'; out+=c; }
    return out+'"';
}
void write(const fs::path& p,const std::string& text) {
    std::ofstream out(p,std::ios::binary); out<<text; out.close(); require(bool(out),"cannot write private fixture");
}
struct Scratch {
    fs::path path;
    Scratch() { std::string p="/private/tmp/schgen-purity-config-XXXXXX"; const auto* r=::mkdtemp(p.data()); require(r!=nullptr,"mkdtemp"); path=r; }
    ~Scratch() { std::error_code error; fs::remove_all(path,error); }
};
template<class F> void rejects(F&& f,const std::string& why) {
    bool rejected=false; try { f(); } catch (const std::exception&) { rejected=true; } require(rejected,why);
}
}
int main(int argc,char** argv) {
    try {
        require(argc>=5,"usage: contracts REPOSITORY COMPILER LIBCLANG SYSTEM_INCLUDE...");
        const auto root=fs::canonical(argv[1])/"native/tests/data/authoring_purity";
        const auto compiler=fs::canonical(argv[2]).string();
        Scratch scratch;
        const auto database=scratch.path/"commands.json", configuration=scratch.path/"toolchain.json";
        std::string includes;
        for (int i=4;i<argc;++i) { if (!includes.empty()) includes+=','; includes+=quote(fs::canonical(argv[i]).string()); }
        const auto config=[&](const std::string& extra={}) {
            return "{\"schema\":\"schgen.authoring-purity.toolchain.v1\",\"compiler\":"+quote(compiler)+
                ",\"libclang\":"+quote(fs::canonical(argv[3]).string())+",\"compile_commands\":"+quote(database.string())+
                ",\"system_include_directories\":["+includes+"],\"production_targets\":[\"schgen_core\"]"+extra+"}";
        };
        const auto entry=[&](const std::string& file,const std::string& extra={}) {
            return "{\"directory\":"+quote(root.string())+",\"file\":"+quote(file)+",\"output\":\"CMakeFiles/schgen_core.dir/fixture.o\",\"arguments\":["+quote(compiler)+
                ",\"-std=c++17\",\"-Wall\",\"-Werror\",\"-ffp-contract=off\",\"-O2\",\"-c\","+quote(file)+
                ",\"-o\",\"CMakeFiles/schgen_core.dir/fixture.o\""+extra+"]}";
        };
        const auto load=[&] { return schgen::load_authoring_purity_configuration(root,configuration); };
        write(configuration,config()); write(database,"["+entry("subject.cpp")+","+entry("helper.cpp")+"]");
        const auto good=load();
        require(good.commands.size()==2 && good.commands[0].arguments==std::vector<std::string>{"-O2"},"compile argv normalization");
        require(good.toolchain.system_include_directories.size()==std::size_t(argc-4),"explicit trust roots preserved");
        auto observed=entry("subject.cpp",",\"-finstrument-functions\",\"-fno-inline\"");
        for (std::size_t pos=0;(pos=observed.find("schgen_core.dir",pos))!=std::string::npos;pos+=29)
            observed.replace(pos,15,"schgen_precision_observed.dir");
        write(database,"["+observed+","+entry("subject.cpp")+","+entry("helper.cpp")+"]");
        require(load().commands.size()==2,"unrelated instrumented command before production must not affect target-authorized selection");
        write(database,"["+entry("subject.cpp",",\"-finstrument-functions\"")+"]");
        rejects(load,"unsupported instrumentation in the selected production target cannot be ignored");
        auto wrong_output=entry("subject.cpp");
        const auto object=wrong_output.rfind("CMakeFiles/schgen_core.dir/fixture.o");
        wrong_output.replace(object,std::string("CMakeFiles/schgen_core.dir/fixture.o").size(),"CMakeFiles/other.dir/fixture.o");
        write(database,"["+wrong_output+"]"); rejects(load,"argv output cannot disagree with claimed target authority");
        schgen::AuthoringPurityScope scope;
        scope.units={"subject.cpp","helper.cpp"}; scope.headers={"api.hpp"}; scope.census_roots={"."};
        scope.constructors={"subject.cpp::schgen::circuit | schgen::CircuitSheetIr (const schgen::SubsystemMeta &, const schgen::AuthoringContext &)"};
        scope.infrastructure={"api.hpp::schgen::net | void (schgen::CircuitSheetIr &)"};
        require(schgen::check_authoring_purity(root,scope,good.commands,good.toolchain).ok(),"real compiler through loaded config");
        write(database,"["+entry("subject.cpp")+","+entry("subject.cpp")+"]");
        require(load().commands.size()==1,"identical target commands deduplicate without losing evidence");
        write(database,"["+entry("subject.cpp")+","+entry("subject.cpp",",\"-DPURITY_CASE=1\"")+"]");
        rejects(load,"different target preprocessing cannot be silently selected");
        for (const auto* arg:{"@secret.rsp","-fmodules","-fdelayed-template-parsing","-Xclang","-Wp,-DPURITY_CASE=1","-std=gnu++17","-ffp-contract=fast"}) {
            write(database,"["+entry("subject.cpp",","+quote(arg))+"]"); rejects(load,std::string("opaque compiler argument accepted: ")+arg);
        }
        write(database,"["+entry("subject.cpp",",\"-isystem\",\".\",\"-iquote\",\".\"")+"]");
        const auto paths=load().commands[0].arguments;
        require(paths==std::vector<std::string>{"-O2","-isystem",root.string(),"-iquote",root.string()},"preserve include precedence; path alone does not confer trust");
        const auto command_entry=[&](const std::string& command) {
            return "[{\"directory\":"+quote(root.string())+",\"file\":\"subject.cpp\",\"output\":\"CMakeFiles/schgen_core.dir/fixture.o\",\"command\":"+quote(command)+"}]";
        };
        write(database,command_entry("'"+compiler+"' -c 'subject.cpp' -o 'CMakeFiles/schgen_core.dir/fixture.o' -D'NOTE=hello world'"));
        require(load().commands[0].arguments==std::vector<std::string>{"-DNOTE=hello world"},"quoted command parsed without a shell");
        for (const auto* suffix:{"; touch escaped"," $(touch escaped)"," `touch escaped`"," @args"," 'unterminated"}) {
            write(database,command_entry(compiler+" -c subject.cpp"+suffix)); rejects(load,"shell syntax accepted");
        }
        write(database,"["+entry("subject.cpp")+"]");
        write(configuration,config(",\"allow_geometry\":true")); rejects(load,"configuration must not grant exceptions");
        write(configuration,config(",\"enabled\":false")); rejects(load,"configuration must not disable the gate");
        write(configuration,"{}");
        require(!schgen::check_native_authoring_purity(root,configuration,schgen::AuthoringContext{}).ok(),"production context/configuration failure report");
        require(!schgen::check_native_authoring_purity_census(root,configuration).ok(),"census configuration failure report");
        write(configuration,config()); write(database,"[]"); rejects(load,"empty database");
        std::cout<<"authoring purity configuration: "<<checks<<" contracts PASS\n";
    } catch (const std::exception& error) { std::cerr<<error.what()<<'\n'; return 1; }
}
