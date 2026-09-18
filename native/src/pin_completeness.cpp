#include "schgen/pin_completeness.hpp"
#include "verification_internal.hpp"

namespace schgen {
using namespace verification;
NcAllowlist nc_allowlist_from_json(const JsonNode& root) {
    if(root.kind!=JsonKind::Object)throw std::invalid_argument("NC allowlist must be an object");
    NcAllowlist out;for(const auto& [sheet,rows]:root.object_value) {
        if(!sheet.empty()&&sheet.front()=='_'&&rows.kind!=JsonKind::Object)continue;
        if(rows.kind!=JsonKind::Object)throw std::invalid_argument("NC allowlist sheet must be an object: "+sheet);
        for(const auto& [ref,pins]:rows.object_value) {
            if(pins.kind!=JsonKind::Array)throw std::invalid_argument("NC allowlist pins must be an array");
            for(const auto& pin:pins.array_value) {
                if(pin.kind!=JsonKind::String)throw std::invalid_argument("NC allowlist pin must be a string");
                out[sheet][ref].insert(pin.string_value);
            }
        }
    }return out;
}
NcAllowlist load_nc_allowlist(const std::filesystem::path& path){return std::filesystem::exists(path)?nc_allowlist_from_json(parse_json_file(path.string())):NcAllowlist{};}
PinCompletenessResult check_pin_completeness(const std::vector<ProjectCircuit>& sheets,const SchematicSymbolResolver& resolve,const NcAllowlist& allow) {
    PinCompletenessResult out;
    for(const auto& sheet:sheets) {
        std::map<std::string,std::set<std::string>> netted,nc;
        for(const auto& net:sheet.circuit.nets)for(const auto& p:net.pins)netted[p.ref].insert(p.pin);
        for(const auto& p:sheet.circuit.nc)nc[p.ref].insert(p.pin);
        for(const auto* part:ordered_parts(sheet.circuit)) {
            const auto& symbol=resolve(part->lib_id);std::set<std::string> pins;std::map<std::string,std::string> names;
            for(const auto& pin:symbol.pins){pins.insert(pin.number);names[pin.number]=pin.name;}
            if(pins.size()<2)continue;++out.parts_checked;
            std::vector<std::string> floats;
            for(const auto& p:pins)if(!netted[part->ref].count(p)&&!nc[part->ref].count(p))floats.push_back(p);
            std::sort(floats.begin(),floats.end(),pin_less);
            if(!floats.empty()) {out.ok=false;for(auto& p:floats)p+="("+names[p]+")";
                out.floats.push_back(sheet.name+":"+part->ref+" ("+part->value+") silent float pin(s): "+join(floats,", "));}
            std::set<std::string> blessed;
            const auto a=allow.find(sheet.name);
            if(a!=allow.end()){const auto b=a->second.find(part->ref);if(b!=a->second.end())blessed=b->second;}
            auto cp=std::vector<std::string>(nc[part->ref].begin(),nc[part->ref].end());std::sort(cp.begin(),cp.end(),pin_less);
            for(const auto& p:cp) {
                (blessed.count(p)?out.nc_seeded:out.nc_new).push_back(sheet.name+":"+part->ref+"."+p+" ("+part->value+" "+names[p]+")");++out.nc_total;
            }
        }
    }return out;
}
PinCompletenessResult check_pin_completeness(const std::vector<ProjectCircuit>& s,SymbolLibrary& l,const NcAllowlist& a){return check_pin_completeness(s,[&](const auto& id)->const SymbolDef&{return l.get(id);},a);}
std::string PinCompletenessResult::report() const {
    std::vector<std::string> lines{"pin completeness gate (every multi-pin IC pin is NETTED or explicit NC)",std::string(64,'='),
        "STATUS: REPORT-FIRST (does NOT fail the board yet; promotes to HARD-FAIL once the NC allowlist is fully blessed)",
        std::to_string(parts_checked)+" multi-pin parts checked; "+std::to_string(nc_total)+" author-declared NC pins"};
    if(floats.empty())lines.push_back("silent floats: none");
    else {lines.push_back("");lines.push_back("SILENT FLOATS ("+std::to_string(floats.size())+") — pin neither netted nor NC (probable missing connection):");for(const auto& s:floats)lines.push_back("  "+s);}
    lines.push_back("");lines.push_back("NC ALLOWLIST — "+std::to_string(nc_seeded.size())+" blessed [seed], "+std::to_string(nc_new.size())+" to bless [new]:");
    for(const auto& s:nc_seeded)lines.push_back("  [seed] "+s);for(const auto& s:nc_new)lines.push_back("  [new]  "+s);return join(lines);
}
PinCompletenessResult run_pin_completeness(const std::vector<ProjectCircuit>& s,SymbolLibrary& l,const NcAllowlist& a,const std::filesystem::path& d){auto r=check_pin_completeness(s,l,a);write_report(d/"pin_completeness.txt",r.report());return r;}
JsonNode pin_completeness_result_json(const PinCompletenessResult& r){return obj({{"ok",j(r.ok)},{"parts_checked",j(double(r.parts_checked))},{"nc_total",j(double(r.nc_total))},{"floats",strings(r.floats)},{"nc_seeded",strings(r.nc_seeded)},{"nc_new",strings(r.nc_new)},{"report",j(r.report())}});}
}  // namespace schgen
