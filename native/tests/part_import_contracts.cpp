#include "schgen/part_import.hpp"
#include "schgen/atomic_file.hpp"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <tuple>
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
std::vector<CatalogPin> pins(const JsonNode& rows){
    std::vector<CatalogPin> out;
    for(const auto& row:rows.array_value)out.push_back({field(row,"number").string_value,field(row,"name").string_value,field(row,"etype").string_value});
    return out;
}
void same_pins(const std::vector<CatalogPin>& actual,const JsonNode& expected,const std::string& message){
    const auto want=pins(expected);require(actual.size()==want.size(),message+" count");
    for(std::size_t i=0;i<want.size();++i)
        require(std::tie(actual[i].number,actual[i].name,actual[i].etype)==std::tie(want[i].number,want[i].name,want[i].etype),message+" pin "+std::to_string(i));
}
std::string unhex(const std::string& text){
    if(text.size()%2)throw std::runtime_error("odd hex fixture");std::string out;
    for(std::size_t i=0;i<text.size();i+=2)out+=static_cast<char>(std::stoul(text.substr(i,2),nullptr,16));return out;
}
std::string hex(const std::string& bytes){
    constexpr char chars[]="0123456789abcdef";std::string out;
    for(const unsigned char c:bytes){out+=chars[c>>4];out+=chars[c&15];}return out;
}
void utilities(const std::filesystem::path& directory,const std::string& self){
    const auto reference=parse_json_file((directory.parent_path()/"part_import_utilities/python.json").string());
    for(const auto& row:field(reference,"safe_names").array_value)
        exact(part_safe_name(field(row,"input").string_value),field(row,"output").string_value,"safe-name utility");
    const auto& raw_info=field(reference,"info");PartImportInfo info;auto& p=info.part;
    p.prefix=field(raw_info,"prefix").string_value;p.mpn=field(raw_info,"mpn").string_value;
    p.description=field(raw_info,"description").string_value;p.datasheet=field(raw_info,"datasheet").string_value;p.lcsc=field(raw_info,"lcsc").string_value;
    for(const auto& row:field(reference,"groups").array_value){
        const auto input=pins(field(row,"pins"));const auto g=part_group_pins(input);const auto& want=field(row,"groups");
        same_pins(g.left,field(want,"left"),"group left");same_pins(g.right,field(want,"right"),"group right");
        same_pins(g.top,field(want,"top"),"group top");same_pins(g.bottom,field(want,"bottom"),"group bottom");
        exact(part_next_pin_number(input),field(row,"next").string_value,"unbounded EP pin number");
        for(const auto& [prefix,expected]:field(row,"normalized").object_value)
            same_pins(part_normalize_pin_types(input,prefix),expected,"normalize "+prefix);
        const auto ep=part_synthesize_ep("C3192119",input);const auto& expected=field(row,"ep");
        require(bool(ep)==(expected.kind!=JsonKind::Null),"EP duplicate suppression");
        if(ep)require(ep->number==field(expected,"number").string_value && ep->name=="EP" && ep->etype=="passive","EP metadata");
        require(!part_synthesize_ep("C0",input) && !part_synthesize_ep("",input),"EP not allowlisted");
        exact(sexpr_dumps(part_generate_symbol("test",input,info)),field(row,"symbol").string_value,"parameterized synthetic symbol");
    }
    same_pins(part_import_pins(field(field(reference,"parse"),"input")),field(field(reference,"parse"),"pins"),"parse pin fallbacks");
    const auto pads=part_ep_pad_nodes("99","C3192119"),silk=part_silk_plus_nodes("C5365933");
    require(pads.size()==1 && silk.size()==2,"EP/polarity shape count");
    exact(sexpr_dumps(pads[0]),field(reference,"ep_pad").array_value[0].string_value,"EP copper paste mask stack");
    for(std::size_t i=0;i<silk.size();++i)exact(sexpr_dumps(silk[i]),field(reference,"silk").array_value[i].string_value,"RTC pad-1 polarity");
    require(part_silk_plus_nodes("unknown").empty(),"polarity not allowlisted");
    rejects([&]{part_ep_pad_nodes("9","unknown");},"EP missing specification rejected");

    const auto& gzip=field(reference,"gzip");const auto gzip_hex=field(gzip,"hex").string_value;
    const auto compressed=unhex(gzip_hex),plain=field(gzip,"plain").string_value;
    const auto transport=part_curl_transport({},self);
    // A real subprocess runs this executable's curl-fixture mode. No injected
    // response/runner can bypass the process capture boundary being tested.
    PartHttpRequest request{"https://example.invalid/binary/"+gzip_hex};
    const auto response=transport(request);
    require(response.status==200 && response.transport_error.empty(),"real binary child transport succeeded");
    exact(response.body,compressed,"real subprocess retained gzip bytes including invalid UTF8/NUL");
    exact(part_http_body(request,response),plain,"real subprocess gzip body decompressed");
    const auto binary=std::string("ISO-10303-21;\r\n\xff\0",17);
    request.url="https://example.invalid/binary/"+hex(binary);
    exact(part_http_body(request,transport(request)),binary,"real subprocess retains STEP CRLF and non-UTF8 bytes");
    exact(part_http_body(request,{200,compressed+compressed,{}}),plain+plain,"concatenated gzip members");
    request.max_bytes=compressed.size()*2;
    rejects([&]{part_http_body(request,{200,compressed.substr(0,compressed.size()-2),{}});},"truncated gzip trailer fails");
    request.max_bytes=3;
    rejects([&]{part_http_body(request,{200,compressed,{}});},"gzip compressed size cap");

    std::vector<std::string> observed;std::chrono::milliseconds timeout{0};
    const auto runner=[&](const std::vector<std::string>& argv,std::chrono::milliseconds t){observed=argv;timeout=t;return ProcessResult{0,"ok\nSCHGEN_HTTP_STATUS:204",""};};
    const auto injected=part_curl_transport(runner);PartHttpRequest normal{"https://example.invalid/part",std::chrono::milliseconds{2345},77};
    require(injected(normal).status==204 && timeout.count()==3345,"curl explicit timeout with process grace");
    auto option=[&](const std::string& flag){const auto at=std::find(observed.begin(),observed.end(),flag);require(at!=observed.end() && at+1!=observed.end(),"curl option "+flag);return *(at+1);};
    require(option("--max-time")=="2.345" && option("--max-filesize")=="77","curl bounds transported");
    require(option("--proto")=="=https" && option("--proto-redir")=="=https","curl redirect scheme restriction");
    require(!injected({"http://example.invalid"}).transport_error.empty(),"HTTP downgrade rejected");
    require(!part_curl_transport([](const auto&,auto){return ProcessResult{7,"","connection refused"};})(normal).transport_error.empty(),"curl exit failure surfaced");
    require(!part_curl_transport([](const auto&,auto){return ProcessResult{0,"missing trailer",""};})(normal).transport_error.empty(),"missing HTTP status surfaced");
    require(!part_curl_transport([](const auto&,auto)->ProcessResult{throw ProcessTimeout("deadline");})(normal).transport_error.empty(),"process timeout surfaced");
    rejects([&]{fetch_part_cad("C1",[](const auto&){return PartHttpResponse{503,"busy",{}};});},"CAD HTTP status rejected");
    rejects([&]{fetch_part_cad("C1",[](const auto&){return PartHttpResponse{200,"<html>",{}};});},"CAD non-JSON rejected");
    rejects([&]{fetch_part_cad("C1",[](const auto&){return PartHttpResponse{200,"{\"success\":false}",{}};});},"CAD unavailable result rejected");
    const std::string cad="{\"success\":true,\"result\":{}}";
    exact(fetch_part_cad("C1",[&](const auto&){return PartHttpResponse{200,cad,{}};}),cad,"CAD response retained");

    const auto models_reference=parse_json_file((directory.parent_path()/"render_models/reference.json").string());
    std::string obj,wrl;
    for(const auto& row:field(models_reference,"obj").array_value){
        if(field(row,"output").kind==JsonKind::String){obj=field(row,"input").string_value;wrl=field(row,"output").string_value;break;}
    }
    require(!obj.empty(),"independent OBJ conversion reference exists");
    const std::string step="ISO-10303-21;\r\n"+std::string(220,' ');std::size_t calls=0;
    const PartTransport both=[&](const auto& r){++calls;return PartHttpResponse{200,r.url.find("3dmodel/")!=std::string::npos?obj:step,{}};};
    const auto models=fetch_part_models("fixture-uuid","part",both);
    require(calls==2 && models.files.size()==2 && models.diagnostics.empty(),"STEP plus OBJ downloaded");
    exact(models.files[0].bytes,wrl,"download uses independently verified OBJ converter");
    exact(models.files[1].bytes,step,"STEP bytes retained");
    require(models.files[0].name=="part.wrl" && models.files[1].name=="part.step","WRL preferred before STEP");
    const auto failed=fetch_part_models("fixture-uuid","part",[](const auto&){return PartHttpResponse{404,"missing",{}};});
    require(failed.files.empty() && failed.diagnostics.size()==2 && failed.diagnostics.front().find("404")!=std::string::npos,"optional asset HTTP errors remain visible");
    const auto invalid=fetch_part_models("fixture-uuid","part",[](const auto&){return PartHttpResponse{200,"not a model",{}};});
    require(invalid.files.empty() && invalid.diagnostics.size()==2,"invalid model content remains visible");
    require(fetch_part_models("","part",{}).files.empty(),"no UUID requires no transport");
    Scratch scratch;
    const auto outdir=scratch.path/"models";
    require(publish_part_models({},outdir,"part").empty() && !std::filesystem::exists(outdir),"empty assets do not create directory");
    const auto written=publish_part_models(models,outdir,"part");
    require(written==std::vector<std::string>{"part.wrl","part.step"},"model-only publish order");
    exact(read(outdir/"part.wrl"),wrl,"published WRL exact");exact(read(outdir/"part.step"),step,"published STEP exact");
    rejects([&]{publish_part_models(models,outdir,"part");},"model overwrite requires explicit permission");
    require(publish_part_models(models,outdir,"part",true)==written,"model overwrite opt-in");
    auto evil=models;evil.files[1].name="../escape.step";
    rejects([&]{publish_part_models(evil,scratch.path/"not-created","part");},"model path traversal rejected before any write");
    require(!std::filesystem::exists(scratch.path/"not-created"),"failed model preflight leaves filesystem untouched");
    std::filesystem::remove(outdir/"part.step");std::filesystem::create_symlink(outdir/"part.wrl",outdir/"part.step");
    rejects([&]{publish_part_models(models,outdir,"part",true);},"model symlink rejected");
    exact(read(outdir/"part.wrl"),wrl,"symlink model publication left victim untouched");
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
        if(argc>2 && std::string(argv[1])=="--disable"){
            const std::string url=argv[argc-1];const auto at=url.find("/binary/");
            if(at==url.npos)return 9;
            const auto bytes=unhex(url.substr(at+8));
            std::cout.write(bytes.data(),static_cast<std::streamsize>(bytes.size()));std::cout<<"\nSCHGEN_HTTP_STATUS:200";
            std::cerr.write("\xff\0\r\n",4);return 0;
        }
        require(argc==3,"usage: part_import_contracts FIXTURES SCHGEN");
        std::vector<std::filesystem::path> cases;
        for(const auto& item:std::filesystem::directory_iterator(argv[1]))
            if(item.path().extension()==".json")cases.push_back(item.path());
        std::sort(cases.begin(),cases.end());
        require(cases.size()==62,"all 62 recorded parts must be covered");
        for(const auto& path:cases)fixture(path);
        boundaries(cases.front(),argv[2]);
        utilities(argv[1],std::filesystem::absolute(argv[0]).string());
        std::cout<<checks<<" exact native part conversion contracts passed\n";
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
