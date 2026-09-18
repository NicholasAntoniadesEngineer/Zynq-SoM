#include "schgen/bom_values.hpp"
#include "schgen/footprint_pads.hpp"
#include "schgen/pin_completeness.hpp"
#include "schgen/symbol_law.hpp"
#include "schgen/sexpr.hpp"
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <system_error>
#include <unistd.h>

namespace {
using namespace schgen;
namespace fs=std::filesystem;
std::size_t checks=0;
void require(bool value,const std::string& message){++checks;if(!value)throw std::runtime_error(message);}
const JsonNode& field(const JsonNode& j,const std::string& key){auto p=object_field(j,key);if(!p)throw std::runtime_error("missing "+key);return *p;}
void same(const JsonNode& a,const JsonNode& b,const std::string& path) {
    require(a.kind==b.kind,path+": type differs");
    switch(a.kind) {
    case JsonKind::Null:break;
    case JsonKind::Bool:require(a.bool_value==b.bool_value,path+": bool differs");break;
    case JsonKind::String:require(a.string_value==b.string_value,path+": "+a.string_value+" != "+b.string_value);break;
    case JsonKind::Number:require(a.number_value==b.number_value,path+": numeric value differs");break;
    case JsonKind::Array:require(a.array_value.size()==b.array_value.size(),path+": array count differs");for(std::size_t i=0;i<a.array_value.size();++i)same(a.array_value[i],b.array_value[i],path+"["+std::to_string(i)+"]");break;
    case JsonKind::Object:require(a.object_value.size()==b.object_value.size(),path+": object count differs");for(const auto& [key,value]:a.object_value)same(value,field(b,key),path+"."+key);break;
    }
}
std::map<std::string,std::string> string_map(const JsonNode& n){std::map<std::string,std::string> out;for(const auto& [k,v]:n.object_value)out[k]=v.string_value;return out;}
std::set<std::string> string_set(const JsonNode& n){std::set<std::string> out;for(const auto& v:n.array_value)out.insert(v.string_value);return out;}
struct Scratch {
    fs::path path;
    Scratch(){auto name=(fs::temp_directory_path()/"schgen_verification_XXXXXX").string();if(!mkdtemp(name.data()))throw std::runtime_error("mkdtemp failed");path=name;}
    ~Scratch(){std::error_code error;fs::remove_all(path,error);}
};
void write_file(const fs::path& p,const std::string& text){fs::create_directories(p.parent_path());std::ofstream stream(p,std::ios::binary);stream<<text;if(!stream)throw std::runtime_error("fixture write failed");}
std::string read_file(const fs::path& p){std::ifstream stream(p,std::ios::binary);return {std::istreambuf_iterator<char>(stream),{}};}
}
int main(int argc,char** argv) {
    try {
        require(argc==2,"usage: verification_contracts <fixture-directory>");const fs::path dir(argv[1]);
        const auto manifest=parse_json_file((dir/"manifest.json").string());
        const auto catalog=load_bom_value_catalog(dir/"catalog.json");const auto allow=load_nc_allowlist(dir/"allowlist.json");
        const auto pads=parse_json_file((dir/"pads.json").string());std::map<std::string,SymbolDef> symbols;
        for(const auto& [id,row]:parse_json_file((dir/"symbols.json").string()).object_value)
            symbols[id]=parse_symbol(id,sexpr_loads(field(row,"raw").string_value));
        const SchematicSymbolResolver resolve=[&](const auto& id)->const SymbolDef& {const auto it=symbols.find(id);if(it==symbols.end())throw SymbolError("missing "+id);return it->second;};
        const SymbolPinNumberResolver pin_numbers=[&](const auto& id){std::set<std::string> pins;for(const auto& p:resolve(id).pins)pins.insert(p.number);return pins;};
        std::size_t cases=0;
        for(const auto& filename:field(manifest,"cases").array_value) {
            const auto row=parse_json_file((dir/filename.string_value).string());std::vector<ProjectCircuit> sheets;std::vector<CircuitSheetIr> circuits;
            for(const auto& s:field(row,"sheets").array_value){auto c=decode_intermediate_circuit_ir(field(s,"circuit"));circuits.push_back(c);sheets.push_back({field(s,"name").string_value,{},std::move(c)});}
            const auto& expected=field(row,"expected");
            if(const auto* wanted=object_field(expected,"bom")) {
                const auto* cat=object_field(row,"catalog");same(bom_value_result_json(check_bom_values(sheets,cat?bom_value_catalog_from_json(*cat):catalog)),*wanted,filename.string_value+".bom");
            }
            if(const auto* wanted=object_field(expected,"pins")) {
                const auto* a=object_field(row,"allowlist");same(pin_completeness_result_json(check_pin_completeness(sheets,resolve,a?nc_allowlist_from_json(*a):allow)),*wanted,filename.string_value+".pins");
            }
            if(const auto* wanted=object_field(expected,"pads")) {
                std::map<std::string,int> calls;
                const FootprintPadResolver fp=[&](const auto& id)->std::optional<std::set<std::string>>{
                    require(++calls[id]==1,"pad resolver called repeatedly for "+id);
                    const auto* override=object_field(row,"pads");const auto* found=override?object_field(*override,id):nullptr;
                    if(!found)found=object_field(pads,id);if(!found||found->kind==JsonKind::Null)return std::nullopt;return string_set(*found);
                };
                same(footprint_pads_result_json(check_footprint_pads(sheets,pin_numbers,fp)),*wanted,filename.string_value+".pads");
            }
            if(const auto* wanted=object_field(expected,"law")) {
                const auto* p=object_field(row,"pending");same(symbol_law_result_json(check_symbol_law(circuits,resolve,p?string_map(*p):std::map<std::string,std::string>{})),*wanted,filename.string_value+".law");
            }
            ++cases;
        }
        const auto norms=parse_json_file((dir/"norm.json").string());
        for(const auto& row:norms.array_value) {
            const auto& h=field(row,"hint");const auto got=normalize_bom_value(field(row,"value").string_value,h.kind==JsonKind::Null?std::nullopt:std::optional<std::string>(h.string_value));
            const auto& expected=field(row,"expected");require(bool(got)==(expected.kind!=JsonKind::Null),"normalizer presence: "+field(row,"value").string_value);
            if(got){require(got->component_class==expected.array_value[0].string_value,"normalizer class");require(got->magnitude==expected.array_value[1].number_value,"normalizer magnitude");}
        }
        require(equal_bom_values({"R",0},{"R",0}),"zero equality");require(!equal_bom_values({"R",0},{"C",0}),"class equality");
        require(equal_bom_values({"R",995},{"R",1000}),"inclusive tolerance");require(!equal_bom_values({"R",994.999},{"R",1000}),"outside tolerance");
        require(footprint_pad_numbers("(pad \"1\") (pad\n \"2\") (pad \"\") (pad \"1\") (pad 3) (padding \"4\")")==std::set<std::string>({"1","2"}),"quoted/multiline/empty pad scan");
        require(footprint_pad_numbers("(pad\u2003\"A\") (pad \"日本\")")==std::set<std::string>({"A","日本"}),"Unicode pad scan");
        require(!symbol_is_power_flag([](const auto&)->const SymbolDef&{throw SymbolError("unresolved");},"x"),"symbol error skip");
        for(int mode=0;mode<3;++mode) {
            bool caught=false;
            try{symbol_is_power_flag([&](const auto&)->const SymbolDef&{if(mode==0)throw std::bad_alloc();if(mode==1)throw std::system_error(std::make_error_code(std::errc::io_error));throw std::runtime_error("cancel");},"x");}
            catch(const std::exception&){caught=true;}
            require(caught,"non-symbol exception swallowed");
        }
        SymbolDef nested;nested.raw=sexpr_loads("(symbol \"x\" (symbol \"child\" (power)))");
        require(!symbol_is_power_flag([&](const auto&)->const SymbolDef&{return nested;},"x"),"nested power falsely exempted");
        nested.raw=sexpr_loads("(symbol \"x\" (\"power\"))");require(symbol_is_power_flag([&](const auto&)->const SymbolDef&{return nested;},"x"),"string power tag rejected");
        Scratch scratch;const auto root=scratch.path;
        FootprintResolutionOptions options{root/"parts",root/"kicad",{root/"board"/"fp-lib-table"},{{"Alias:One","Alias:Two"},{"Alias:Two","Lib:Stock"}}};
        write_file(root/"board"/"fp-lib-table","(fp_lib_table\n (lib (name \"Lib\") (type \"KiCad\")\n (uri \"${KIPRJMOD}/local.pretty\"))\n (lib (name \"Bad\") (uri \"${UNKNOWN}/missing\")))");
        write_file(root/"board/local.pretty/Same.kicad_mod","(pad \"table\")");
        write_file(root/"parts/Lib/Same.kicad_mod","(pad \"dossier\")");
        write_file(root/"kicad/Lib.pretty/Same.kicad_mod","(pad \"stock\")");
        write_file(root/"kicad/Lib.pretty/Stock.kicad_mod","(pad \"1\")");
        const auto paths=load_footprint_library_tables(options);require(paths.size()==1&&paths.at("Lib")==root/"board/local.pretty","library URI expansion");
        require(resolve_footprint("Lib:Same",paths,options)==root/"parts/Lib/Same.kicad_mod","dossier priority");
        options.parts_dir=root/"absent";require(resolve_footprint("Lib:Same",paths,options)==root/"board/local.pretty/Same.kicad_mod","table priority");
        require(resolve_footprint("Lib:Same",{},options)==root/"kicad/Lib.pretty/Same.kicad_mod","stock fallback");
        require(!resolve_footprint("Alias:One",paths,options),"alias recursion exceeded one hop");
        require(resolve_footprint("Alias:Two",paths,options)==root/"kicad/Lib.pretty/Stock.kicad_mod","one alias hop");
        require(resolve_footprint((root/"parts/Lib/Same.kicad_mod").string(),paths,options)==root/"parts/Lib/Same.kicad_mod","explicit footprint path");
        require(!resolve_footprint((root/"board/fp-lib-table").string(),paths,options),"wrong explicit suffix accepted");
        write_file(root/"invalid.kicad_mod",std::string("(pad \"1")+char(0xff)+"\") (pad \"2\")");
        require(read_footprint_pad_numbers(root/"invalid.kicad_mod")==std::set<std::string>({"1�","2"}),"UTF-8 replacement behavior");
        require(load_nc_allowlist(root/"not-present.json").empty(),"missing NC allowlist");
        const auto report=run_bom_values({},catalog,root);require(read_file(root/"bom_values.txt")==report.report()+"\n","report bytes/final LF");
        bool io_failed=false;try{run_bom_values({},catalog,root/"missing");}catch(const fs::filesystem_error&){io_failed=true;}
        require(io_failed&&!fs::exists(root/"missing"),"BOM writer created a directory unlike Python");
        std::cout<<cases<<" frozen gate cases + "<<norms.array_value.size()<<" normalization vectors; "<<checks<<" exact checks passed\n";
    }catch(const std::exception& e){std::cerr<<"verification contract failure: "<<e.what()<<'\n';return 1;}
}
