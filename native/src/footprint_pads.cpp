#include "schgen/footprint_pads.hpp"
#include "verification_internal.hpp"

namespace schgen {
using namespace verification;
namespace {
std::optional<std::filesystem::path> uri_path(const std::string& uri,const FootprintResolutionOptions& opts) {
    // Preserve the Python helper's search across ALL table parents, not only
    // the table containing this row. Unexpanded dollar variables are skipped.
    for(const auto& table:opts.library_tables) {
        auto path=uri;replace_all(path,"${KIPRJMOD}",table.parent_path().string());
        if(path.find('$')!=std::string::npos)continue;
        if(std::filesystem::exists(path))return std::filesystem::path(path);
    }return std::nullopt;
}
}
FootprintPaths load_footprint_library_tables(const FootprintResolutionOptions& opts) {
    FootprintPaths out;
    static const std::regex rows(R"re(\(lib\s+\(name\s+"([^"]+)"\)[\s\S]*?\(uri\s+"([^"]+)"\))re");
    for(const auto& path:opts.library_tables) {
        if(!std::filesystem::exists(path))continue;
        const auto text=read(path);
        for(auto it=std::sregex_iterator(text.begin(),text.end(),rows);it!=std::sregex_iterator();++it)
            if(auto resolved=uri_path((*it)[2],opts))out[(*it)[1]]=*resolved;
    }
    return out;
}
std::optional<std::filesystem::path> resolve_footprint(const std::string& id,const FootprintPaths& libs,const FootprintResolutionOptions& opts) {
    namespace fs=std::filesystem;const auto colon=id.find(':');
    if(colon==std::string::npos){const fs::path path(id);return fs::is_regular_file(path)&&path.extension()==".kicad_mod"?std::optional<fs::path>(path):std::nullopt;}
    const auto nick=id.substr(0,colon),name=id.substr(colon+1)+".kicad_mod";
    if(!opts.parts_dir.empty()){const auto path=opts.parts_dir/nick/name;if(fs::is_regular_file(path))return path;}
    const auto row=libs.find(nick);if(row!=libs.end()){const auto path=row->second/name;if(fs::is_regular_file(path))return path;}
    if(!opts.kicad_footprint_root.empty()){const auto path=opts.kicad_footprint_root/(nick+".pretty")/name;if(fs::is_regular_file(path))return path;}
    const auto alias=opts.aliases.find(id);
    if(alias!=opts.aliases.end()&&alias->second!=id){auto once=opts;once.aliases.clear();return resolve_footprint(alias->second,libs,once);}
    return std::nullopt;
}
std::set<std::string> footprint_pad_numbers(std::string_view raw) {
    const std::string text(raw);std::set<std::string> out;std::size_t pos=0;
    while((pos=text.find("(pad",pos))!=std::string::npos) {
        pos+=4;std::size_t end=pos;
        // Match Python Unicode \s without rewriting quoted pad names.
        while(end<text.size()) {
            const auto token=utf8(text.substr(end,std::min<std::size_t>(4,text.size()-end))).front();
            if(!space(token.first))break;end+=token.second.size();
        }
        if(end==pos||end>=text.size()||text[end]!='"')continue;
        const auto close=text.find('"',end+1);if(close==std::string::npos)break;
        if(close>end+1)out.insert(text.substr(end+1,close-end-1));pos=close+1;
    }
    return out;
}
std::set<std::string> read_footprint_pad_numbers(const std::filesystem::path& path){return footprint_pad_numbers(replace_invalid_utf8(read(path)));}
FootprintPadsResult check_footprint_pads(const std::vector<ProjectCircuit>& sheets,const SymbolPinNumberResolver& pins,const FootprintPadResolver& resolve) {
    FootprintPadsResult out;std::map<std::string,std::optional<std::set<std::string>>> cache;
    for(const auto& sheet:sheets)for(const auto* part:ordered_parts(sheet.circuit)) {
        const auto& fp=part->footprint;
        if(fp.empty()){out.unresolved.push_back(sheet.name+":"+part->ref+" (no footprint)");continue;}
        auto row=cache.find(fp);if(row==cache.end())row=cache.emplace(fp,resolve(fp)).first;
        if(!row->second){out.unresolved.push_back(sheet.name+":"+part->ref+" footprint "+repr(fp));continue;}
        ++out.checked;const auto& pads=*row->second;std::vector<std::string> missing;
        for(const auto& number:pins(part->lib_id))if(!pads.count(number))missing.push_back(number);
        std::sort(missing.begin(),missing.end(),pin_less);
        if(!missing.empty()) {out.ok=false;out.violations.push_back(sheet.name+":"+part->ref+" ("+part->value+", "+part->lib_id+") footprint "+repr(fp)+
            " has "+std::to_string(pads.size())+" pads — symbol pin(s) "+list_repr(missing)+" have NO pad (guaranteed OPEN)");}
    }
    return out;
}
FootprintPadsResult check_footprint_pads(const std::vector<ProjectCircuit>& sheets,SymbolLibrary& lib,const FootprintResolutionOptions& opts) {
    const auto paths=load_footprint_library_tables(opts);
    return check_footprint_pads(sheets,[&](const auto& id){return lib.pin_numbers(id);},[&](const auto& id)->std::optional<std::set<std::string>>{
        auto path=resolve_footprint(id,paths,opts);if(!path)return std::nullopt;return read_footprint_pad_numbers(*path);});
}
std::string FootprintPadsResult::report() const {
    std::vector<std::string> lines{"footprint pad-coverage gate (every symbol pin NUMBER has a footprint PAD)",std::string(64,'='),
        "STATUS: HARD-FAIL (any symbol pin with no footprint pad fails the board) — the ethernet:T1 25/26 open that motivated it is fixed",
        std::to_string(checked)+" parts with a resolved footprint checked"};
    if(violations.empty())lines.push_back("violations: none");
    else {lines.push_back("");lines.push_back("VIOLATIONS ("+std::to_string(violations.size())+") — symbol pin with NO footprint pad (guaranteed OPEN):");for(const auto& v:violations)lines.push_back("  "+v);}
    if(!unresolved.empty()){lines.push_back("");lines.push_back("UNRESOLVED footprints — reported, NOT failing ("+std::to_string(unresolved.size())+"):");for(const auto& v:std::set<std::string>(unresolved.begin(),unresolved.end()))lines.push_back("  "+v);}
    return join(lines);
}
FootprintPadsResult run_footprint_pads(const std::vector<ProjectCircuit>& s,SymbolLibrary& l,const FootprintResolutionOptions& o,const std::filesystem::path& d){auto r=check_footprint_pads(s,l,o);write_report(d/"footprint_pads.txt",r.report());return r;}
JsonNode footprint_pads_result_json(const FootprintPadsResult& r){return obj({{"ok",j(r.ok)},{"checked",j(double(r.checked))},{"violations",strings(r.violations)},{"unresolved",strings(r.unresolved)},{"report",j(r.report())}});}
}  // namespace schgen
