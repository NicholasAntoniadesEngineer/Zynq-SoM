#include "schgen/manufacturing_exports.hpp"
#include "schgen/pcb_checks.hpp"
#include "manufacturing_exports_internal.hpp"

namespace schgen {
using namespace manufacturing_detail;
namespace {
std::string field_value(const CircuitPartIr& p,const std::string& key){for(const auto& f:p.fields)if(f.key==key)return f.value;return "";}
JsonNode rails(const ManufacturingManifestInput& in,const PowerPolicy& policy){
    std::map<std::string,std::string> fed;std::map<std::string,double> limits,loads;std::map<std::string,std::vector<PowerDraw>> draws;
    std::set<std::string> names;
    for(const auto& r:in.power.regs){fed[r.vout]=r.sheet+":"+r.ref+" "+r.value+" ["+r.kind+"]";limits[r.vout]=r.limit_a;}
    for(const auto& [n,s]:policy.sources){fed.emplace(n,"source: "+s.note);limits.emplace(n,s.amps);}
    for(const auto& [n,v]:in.power.rails){names.insert(n);loads[n]=v;}
    for(const auto& [n,v]:in.power.draws)draws[n]=v;
    for(const auto& s:in.sheets)for(const auto& n:s.circuit.nets)if(n.net_class=="power"||n.net_class=="ground")names.insert(n.name);
    std::vector<JsonNode> out;
    for(const auto& name:names){std::vector<JsonNode> ds;auto values=draws[name];
        std::sort(values.begin(),values.end(),[](const auto& a,const auto& b){return std::tie(a.sheet,a.amps,a.note)<std::tie(b.sheet,b.amps,b.note);});
        for(const auto& d:values)ds.push_back(obj({{"sheet",j(d.sheet)},{"amps",j(decimal_round(d.amps,4))},{"note",j(d.note)}}));
        out.push_back(obj({{"name",j(name)},{"volts",opt(rail_volts(name,policy))},{"limit_a",limits.count(name)?j(decimal_round(limits.at(name),4)):JsonNode{}},{"load_a",j(decimal_round(loads[name],4))},{"source",fed.count(name)?j(fed.at(name)):JsonNode{}},{"draws",arr(std::move(ds))}}));
    }return arr(std::move(out));
}
JsonNode i2c(const std::vector<ProjectCircuit>& sheets){
    std::map<std::string,const CircuitSheetIr*> cs;for(const auto& sc:sheets)cs[sc.name]=&sc.circuit;
    using Row=std::tuple<int,std::string,std::string,std::string,std::string>;std::vector<Row> rows;
    for(const auto& [name,ptr]:cs){const auto& c=*ptr;
        if(std::any_of(c.parts.begin(),c.parts.end(),[](const auto& p){return has(p.value,"TCA9535");})){const auto e=bringup_expander(c);rows.emplace_back(e.addr,"TCA9535",name,e.ref,"STM32_I2C2");}
        for(const auto& m:ina3221_monitors(c))rows.emplace_back(m.addr,"INA3221",name,m.ref,"STM32_I2C2");
        for(const auto& p:c.parts)if(has(p.value,"FUSB302"))rows.emplace_back(0x22,"FUSB302B",name,p.ref,"STM32_I2C2");
        if(name=="board_services"){rows.emplace_back(bringup_id_eeprom_addr(c),"24AA025E48",name,"U1","AUX_I2C");rows.emplace_back(0x52,"RV-3028",name,"U2","AUX_I2C");}
    }std::sort(rows.begin(),rows.end());std::vector<JsonNode> out;
    for(const auto& [addr,dev,sheet,ref,bus]:rows)out.push_back(obj({{"device",j(dev)},{"addr",j(addr)},{"addr_hex",j("0x"+hex(addr))},{"bus",j(bus)},{"sheet",j(sheet)},{"ref",j(ref)}}));
    return arr(std::move(out));
}
JsonNode bom(const ManufacturingManifestInput& in){
    std::set<std::tuple<std::string,std::string,std::string>> groups;std::vector<std::string> missing;std::size_t count=0;
    for(const auto& sc:in.sheets)for(const auto& p:sc.circuit.parts){
        if(field_value(p,"BOM")=="exclude")continue;++count;auto lcsc=field_value(p,"LCSC");if(lcsc.empty())missing.push_back(sc.name+":"+p.ref);groups.emplace(p.value,p.footprint,lcsc);
    }
    std::sort(missing.begin(),missing.end());std::vector<JsonNode> ms;for(const auto& s:missing)ms.push_back(j(s));
    return obj({{"lines",j(groups.size())},{"parts",j(count)},{"missing",arr(std::move(ms))},{"cost",in.preflight.cost?j(decimal_round(*in.preflight.cost,4)):JsonNode{}},{"extended",in.preflight.extended?j(static_cast<double>(*in.preflight.extended)):JsonNode{}}});
}
}
std::vector<ProjectArtifact> manufacturing_artifacts(const std::filesystem::path& root,const std::filesystem::path& out){
    namespace fs=std::filesystem;
    std::map<std::string,fs::path> selected;const auto exclude=fs::weakly_canonical(out);
    const auto add=[&](const fs::path& p){if(fs::is_regular_file(p)&&fs::weakly_canonical(p)!=exclude)selected[p.lexically_relative(root).generic_string()]=p;};
    for(const auto& rel:{"Zynq_Carrier.kicad_sch","Zynq_Carrier.kicad_pro","Zynq_Carrier.kicad_pcb","manufacturing/SI_CONSTRAINTS.md","docs/BRINGUP.md","docs/FLOORPLAN.md","docs/DESIGN_SPEC.md","docs/COMPLIANCE.md"})add(root/rel);
    for(const auto& [dir,ext]:ProjectStrings{{"schematic",".kicad_sch"},{"fpga",".xdc"},{"firmware",".h"},{"manufacturing",".csv"},{"manufacturing",".txt"},{"manufacturing",".kicad_dru"},{"reports",".txt"},{"docs",".svg"}}){
        const auto p=root/dir;if(!fs::exists(p))continue;
        for(const auto& entry:fs::directory_iterator(p))if(ends(entry.path().filename().string(),ext))add(entry.path());
    }
    std::vector<ProjectArtifact> result;for(const auto& [rel,p]:selected)result.push_back({rel,pcb_sha256(read(p))});return result;
}
std::optional<std::string> manufacturing_xdc_device(const std::filesystem::path& path){
    if(path.empty()||!std::filesystem::exists(path))return std::nullopt;
    const auto contents=read(path);std::string line;
    const auto check=[&]()->std::optional<std::string>{if(!starts(line,"# Device:"))return std::nullopt;const auto s=verification::strip(line.substr(9));return s.empty()?std::nullopt:std::optional<std::string>(s);};
    for(const auto& [cp,bytes]:verification::utf8(contents)){
        if(cp==10||cp==13||cp==11||cp==12||cp==28||cp==29||cp==30||cp==0x85||cp==0x2028||cp==0x2029){if(starts(line,"# Device:"))return check();line.clear();}else line+=bytes;
    }return check();
}
JsonNode manufacturing_manifest(const ManufacturingManifestInput& in,const PowerPolicy& policy){
    if(in.preflight.extended){const double n=static_cast<double>(*in.preflight.extended);if(n>=9223372036854775808.0||static_cast<long long>(n)!=*in.preflight.extended)throw ProjectError("manifest extended count loses precision in JsonNode; use text rendering");}
    std::vector<JsonNode> gpio,artifacts,banks;
    for(const auto& [name,n]:in.stm32.nets){(void)name;std::vector<JsonNode> pins;for(const auto& p:n.j_pins)pins.push_back(j(p));gpio.push_back(obj({{"net",j(n.net)},{"port",j(n.port)},{"pin",j(n.pin)},{"j_pins",arr(std::move(pins))}}));}
    for(const auto& a:in.artifacts)artifacts.push_back(obj({{"path",j(a.path)},{"sha256",j(a.sha256)}}));
    if(in.xdc){std::set<int> unique(in.xdc->banks.begin(),in.xdc->banks.end());for(auto bank:unique)banks.push_back(j(bank));}
    const auto device=in.device?in.device:(in.xdc?in.xdc->device:std::nullopt);
    return obj({{"device",opt(device)},{"rails",rails(in,policy)},{"i2c_map",i2c(in.sheets)},{"gpio_map",arr(std::move(gpio))},{"xdc",obj({{"pins",in.xdc?j(in.xdc->count):JsonNode{}},{"banks",arr(std::move(banks))}})},{"bom",bom(in)},{"testpoints",obj({{"covered",j(in.coverage.covered)},{"required",j(in.coverage.required)},{"waived",j(in.coverage.waived)}})},{"artifacts",arr(std::move(artifacts))}});
}
std::string render_manufacturing_manifest(const ManufacturingManifestInput& in,const PowerPolicy& policy){
    auto copy=in;copy.preflight.extended.reset();auto out=dump(manufacturing_manifest(copy,policy));
    if(in.preflight.extended){const std::string field="\"extended\": null";const auto p=out.find(field);if(p==out.npos)throw ProjectError("manifest extended field missing");out.replace(p,field.size(),"\"extended\": "+std::to_string(*in.preflight.extended));}
    return out+"\n";
}
} // namespace schgen
