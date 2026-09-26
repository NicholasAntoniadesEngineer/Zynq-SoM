#include "schgen/part_import.hpp"
#include "schgen/atomic_file.hpp"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <unistd.h>

namespace {
using namespace schgen;
std::size_t checks=0;
void require(bool value,const std::string& message){
    ++checks;if(!value)throw std::runtime_error(message);
}
void exact(const std::string& actual,const std::string& expected,const std::string& message){
    ++checks;if(actual==expected)return;
    const auto at=static_cast<std::size_t>(std::mismatch(actual.begin(),actual.end(),expected.begin(),expected.end()).first-actual.begin());
    throw std::runtime_error(message+" at byte "+std::to_string(at)+"\nactual: "+actual.substr(at,160)+"\nexpected: "+expected.substr(at,160));
}
const JsonNode& field(const JsonNode& node,const std::string& key){
    const auto* value=object_field(node,key);
    if(!value)throw std::runtime_error("missing reference field "+key);
    return *value;
}
const std::string& file(const PartImportPlan& plan,const std::string& name){
    const auto found=std::find_if(plan.files.begin(),plan.files.end(),[&](const auto& f){return f.name==name;});
    require(found!=plan.files.end(),"missing generated file "+name);return found->bytes;
}
void fixture(const std::filesystem::path& path){
    const auto reference=parse_json_file(path.string());
    const auto name=field(reference,"name").string_value;
    const auto lcsc=field(reference,"lcsc").string_value;
    const auto input=field(reference,"input").string_value;
    for(const auto& variant:field(reference,"variants").array_value){
        std::vector<std::string> models;
        for(const auto& m:field(variant,"models").array_value)models.push_back(m.string_value);
        const auto plan=prepare_part_import(input,lcsc,name,models);
        exact(file(plan,name+".kicad_sym"),field(reference,"symbol").string_value,
                name+": independent symbol bytes differ");
        exact(file(plan,name+".kicad_mod"),field(variant,"footprint").string_value,
                name+": independent footprint bytes differ");
        exact(file(plan,"part.json"),field(variant,"part_json").string_value,
                name+": independent metadata bytes differ");
        require(file(plan,name+".easyeda.json")==input,name+": raw provider response changed");
        require(plan.files.size()==4,name+": conversion unexpectedly wrote extra assets");
    }
}
template<class F>void rejects(F action,const std::string& message){
    bool rejected=false;try{action();}catch(const PartImportError&){rejected=true;}
    require(rejected,message);
}
struct Scratch{
    std::filesystem::path path;
    Scratch(){
        auto pattern=(std::filesystem::canonical(std::filesystem::temp_directory_path())/"schgen-part-import-XXXXXX").string();
        const auto result=::mkdtemp(pattern.data());require(result!=nullptr,"private import fixture directory");path=result;
    }
    ~Scratch(){std::error_code ignored;std::filesystem::remove_all(path,ignored);}
};
std::string read(const std::filesystem::path& path){
    std::ifstream stream(path,std::ios::binary);require(bool(stream),"read private import output");
    return {std::istreambuf_iterator<char>(stream),{}};
}
void boundaries(const std::filesystem::path& reference_path,const std::string& executable){
    const auto reference=parse_json_file(reference_path.string());
    const auto input=field(reference,"input").string_value,name=field(reference,"name").string_value;
    const auto lcsc=field(reference,"lcsc").string_value;
    rejects([&]{prepare_part_import("{bad");},"malformed input cannot import");
    rejects([&]{prepare_part_import(input,lcsc,"..");},"unsafe output component cannot import");
    rejects([&]{prepare_part_import(input,lcsc,name,{"outside.step"});},"unrelated model cannot import");
    rejects([&]{prepare_part_import(input,lcsc,name,{name+".step",name+".step"});},"duplicate models cannot import");
    PartHttpRequest request{"https://example.invalid/component"};
    require(part_http_body(request,{200,"ok",{}})=="ok","successful HTTP body retained");
    rejects([&]{part_http_body(request,{404,"missing",{}});},"HTTP errors fail explicitly");
    rejects([&]{part_http_body(request,{200,"ok","timeout"});},"transport error cannot masquerade as success");
    request.max_bytes=1;
    rejects([&]{part_http_body(request,{200,"too long",{}});},"body size limit enforced");
    request.max_bytes=1024;
    rejects([&]{part_http_body(request,{200,std::string("\x1f\x8b",2),{}});},"truncated gzip rejected");
    std::size_t calls=0;
    const PartTransport forbidden=[&](const PartHttpRequest&)->PartHttpResponse{++calls;throw PartImportError("offline import contacted network");};
    rejects([&]{fetch_part_cad("../../escape",forbidden);},"URL path injection rejected");
    require(calls==0,"invalid identifier rejected before network");
    Scratch scratch;
    const auto source=scratch.path/"input.json";
    write_atomic_file(source.string(),{input.begin(),input.end()});
    PartImportRequest offline{lcsc,name,scratch.path/"parts",source};
    const auto plan=prepare_part_import_request(offline,forbidden);
    require(calls==0,"offline replay must never use transport");
    const auto output=publish_part_import(plan,offline.parts_root);
    for(const auto& generated:plan.files)exact(read(output/generated.name),generated.bytes,"published bytes changed");
    rejects([&]{publish_part_import(plan,offline.parts_root);},"existing files require explicit overwrite");
    require(publish_part_import(plan,offline.parts_root,true)==output,"authorized overwrite succeeds");
    const auto victim=output/"part.json";
    std::filesystem::remove(victim);std::filesystem::create_symlink(source,victim);
    rejects([&]{publish_part_import(plan,offline.parts_root,true);},"symlink target rejected even with overwrite");
    exact(read(source),input,"symlink destination was modified");
    const auto cli_root=scratch.path/"cli-parts";
    std::vector<std::string> command{executable,"part-import","--parts-root",cli_root.string(),"--from-json",source.string()};
    auto result=run_process(command);
    require(result.exit_code==0,"standalone offline importer failed: "+result.stderr_text);
    for(const auto& generated:plan.files)exact(read(cli_root/name/generated.name),generated.bytes,"CLI output differs from independent conversion");
    require(run_process(command).exit_code!=0,"CLI silently overwrote existing part");
    command.push_back("--overwrite");require(run_process(command).exit_code==0,"explicit CLI overwrite failed");
    command.insert(command.end(),{"--name","one","--name","two"});
    require(run_process(command).exit_code!=0,"duplicate CLI option accepted");
    require(!std::filesystem::exists(cli_root/"two"),"parse failure published a part");
}
}
int main(int argc,char** argv){
    try{
        require(argc==3,"usage: part_import_contracts FIXTURES SCHGEN");
        std::vector<std::filesystem::path> cases;
        for(const auto& item:std::filesystem::directory_iterator(argv[1]))
            if(item.path().extension()==".json")cases.push_back(item.path());
        std::sort(cases.begin(),cases.end());
        require(cases.size()==62,"all 62 recorded parts must be covered");
        for(const auto& path:cases)fixture(path);
        boundaries(cases.front(),argv[2]);
        std::cout<<checks<<" exact native part conversion contracts passed\n";
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
