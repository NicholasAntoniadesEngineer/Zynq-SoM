#include "board_pipeline_internal.hpp"
#include "schgen/validation.hpp"
#include "bringup_unicode.hpp"
#include "gallery_diagram_internal.hpp"

namespace schgen {
namespace {
bool duplicate_directory(const std::string& name){
    const auto cp=document_detail::codepoints(name);std::size_t k=cp.size();
    while(k&&bringup_detail::decimal_digit(cp[k-1])>=0)--k;
    return k<cp.size()&&k&&cp[k-1]==' ';
}
void package_name(const std::string& name){
    if(name.empty()||name.front()=='.'||name.front()=='_'||name.find_first_of("/\\")!=name.npos||name.find('\0')!=name.npos)
        throw ProjectError("invalid native board factory name: "+name);
}
}
BoardAuthoredProject author_board_pipeline_inputs(const ProjectPaths& paths){
    namespace fs=std::filesystem;
    // The registered project identity is its project directory, matching the
    // native author-project frontend. ProjectConfig.name is a human title.
    ProjectAuthoringInput input;input.project_root=paths.project_root;
    input.context=make_authoring_context(paths.repository_root);
    input.som=load_som_interface(paths.som_interface_file);
    input.mapping=link_mapping_from_json(parse_json_file((paths.project_root/"som_mapping.json").string()));
    BoardAuthoredProject out;out.factories=native_project_factories(paths.project_root.filename().string(),input);
    std::sort(out.factories.begin(),out.factories.end(),[](const auto& a,const auto& b){return a.name<b.name;});
    std::set<std::string> names;
    for(const auto& f:out.factories){package_name(f.name);if(!names.insert(f.name).second)throw ProjectError("duplicate native board factory: "+f.name);}
    if(fs::is_directory(paths.subsystems_dir))for(const auto& entry:fs::directory_iterator(paths.subsystems_dir)){
        const auto name=entry.path().filename().string();
        if(name.empty()||name.front()=='.'||name.front()=='_'||duplicate_directory(name))continue;
        if(entry.is_directory()&&!names.count(name))throw ProjectError("unregistered native board package: "+name);
        if(entry.is_directory()&&entry.is_symlink())throw ProjectError("symlinked native board package: "+name);
    }
    SymbolLibrary library(paths.repository_root);
    for(auto& f:out.factories){
        if(!f.circuit)throw ProjectError("missing native board factory: "+f.name);
        auto ir=parse_circuit_ir(authored_circuit_json(f.circuit()));
        if(ir.name!=f.name)throw ProjectError("native board factory name mismatch: "+f.name);
        validate_circuit(ir,library);
        out.circuits.push_back({f.name,paths.subsystems_dir/f.name/"circuit.json",ir});
        f.circuit=[ir=std::move(ir)]{return ir;};
    }
    if(out.circuits.empty())throw ProjectError("board has no native authoring factories");
    return out;
}
void publish_board_pipeline_inputs(BoardAuthoredProject& project,const ProjectPaths& paths,
        const std::filesystem::path& output){
    using namespace board_pipeline_detail;
    if(output.empty())throw ProjectError("native board authoring requires an output tree");
    // Preflight all payloads before replacing a canonical snapshot. The emitted
    // JSON is the same value-owned IR used by the following netlist/gate stages.
    std::vector<std::pair<fs::path,std::string>> files;
    for(const auto& sc:project.circuits){package_name(sc.name);const auto target=output/"subsystems"/sc.name;
        if(fs::is_symlink(target))throw ProjectError("symlinked native board output package: "+sc.name);
        files.emplace_back(target/"circuit.json",json(authored_circuit_json(sc.circuit))+"\n");
        if(fs::weakly_canonical(target)!=fs::weakly_canonical(paths.subsystems_dir/sc.name))
            for(const auto& asset:{std::string("README.md"),sc.name+".cir"}){
                const auto source=paths.subsystems_dir/sc.name/asset;
                if(fs::is_regular_file(source))files.emplace_back(target/asset,read(source));
            }
    }
    for(const auto& [path,bytes]:files)publish_text(path,bytes);
    for(auto& sc:project.circuits)sc.path=output/"subsystems"/sc.name/"circuit.json";
}
}
