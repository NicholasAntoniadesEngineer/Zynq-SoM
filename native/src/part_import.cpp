#include "part_import_internal.hpp"
#include <set>

namespace schgen {
namespace part_import_detail {
void validate_component(const std::string& name) {
    if(name.empty() || name=="." || name==".." || name.find('\0')!=name.npos || name!=part_safe_name(name))
        throw PartImportError("unsafe part path component: "+name);
}
std::string quote(const std::string& text) {
    constexpr char hex[]="0123456789abcdef";std::string out="\"";
    for(const unsigned char ch:text) {
        switch(ch) {
        case '"':out+="\\\"";break;
        case '\\':out+="\\\\";break;
        case '\b':out+="\\b";break;
        case '\f':out+="\\f";break;
        case '\n':out+="\\n";break;
        case '\r':out+="\\r";break;
        case '\t':out+="\\t";break;
        default:if(ch<0x20) {out+="\\u00";out+=hex[ch>>4];out+=hex[ch&15];}else out+=static_cast<char>(ch);
        }
    }
    return out+'"';
}
}
using namespace part_import_detail;

std::string part_metadata_json(const CatalogPart& p) {
    const std::vector<std::pair<std::string,std::string>> fields{{"schema","schgen.part/1"},{"mpn",p.mpn},
        {"safe_name",p.safe_name},{"lcsc",p.lcsc},{"description",p.description},{"manufacturer",p.manufacturer},
        {"package",p.package},{"jlc_class",p.jlc_class},{"prefix",p.prefix},{"datasheet",p.datasheet},
        {"product_url",p.product_url},{"lib_id",p.lib_id},{"footprint",p.footprint}};
    const std::set<std::string> required{"mpn","safe_name","lcsc","description","manufacturer","package","prefix","datasheet","lib_id","footprint"};
    std::string out="{\n";
    for(const auto& [key,value]:fields) {
        if(required.count(key) && value.empty())throw PartImportError("part.json field '"+key+"' must not be empty");
        out+="  "+quote(key)+": "+quote(value)+",\n";
    }
    out+="  \"models_3d\": [";
    for(const auto& f:p.models_3d)out+=( &f==&p.models_3d.front()?"\n":",\n")+std::string("    ")+quote(f);
    if(!p.models_3d.empty())out+="\n  ";out+="],\n  \"pins\": [";
    if(p.pins.empty())throw PartImportError("part.json pins must not be empty");
    for(const auto& pin:p.pins) {
        out+= &pin==&p.pins.front()?"\n":",\n";
        out+="    {\n      \"num\": "+quote(pin.number)+",\n      \"name\": "+quote(pin.name)+",\n      \"etype\": "+quote(pin.etype)+"\n    }";
    }
    return out+"\n  ]\n}\n";
}

std::string part_model_uuid(const JsonNode& result) {
    for(const auto& line:field(field(field(result,"packageDetail"),"dataStr"),"shape").array_value) {
        const auto raw=string(line);if(raw.compare(0,8,"SVGNODE~")!=0)continue;
        try {return get(field(parse_json_text(raw.substr(8)),"attrs"),"uuid");}
        catch(const std::runtime_error&) {return {};}
    }
    return {};
}

PartImportPlan prepare_part_import(const std::string& response_json,const std::string& lcsc,const std::string& requested_name,
                                   const std::vector<std::string>& existing_models,const std::vector<PartImportFile>& downloaded_models) {
    JsonNode payload;
    try {payload=parse_json_text(response_json,"EasyEDA CAD");}
    catch(const std::exception& e) {throw PartImportError(e.what());}
    const auto* wrapped=object_field(payload,"result");const auto& result=wrapped?*wrapped:payload;
    auto info=part_import_info(result);auto& p=info.part;
    if(p.lcsc.empty() && !lcsc.empty())p.lcsc=lcsc;
    p.pins=part_normalize_pin_types(part_import_pins(result),p.prefix);
    const auto ep=part_synthesize_ep(p.lcsc,p.pins);if(ep)p.pins.push_back(*ep);
    p.safe_name=part_safe_name(requested_name.empty()?p.mpn:requested_name);
    if(p.safe_name.empty())throw PartImportError("cannot derive a folder name for "+lcsc);
    validate_component(p.safe_name);
    p.lib_id=p.footprint=p.safe_name+":"+p.safe_name;
    const auto check_model=[&](const std::string& name) {
        if(name!=p.safe_name+".wrl" && name!=p.safe_name+".step")throw PartImportError("unexpected model asset filename: "+name);
        if(std::find(p.models_3d.begin(),p.models_3d.end(),name)!=p.models_3d.end())throw PartImportError("duplicate model asset: "+name);
        p.models_3d.push_back(name);
    };
    PartImportPlan plan;
    if(downloaded_models.empty())for(const auto& model:existing_models)check_model(model);
    else for(const auto& model:downloaded_models) {
        check_model(model.name);if(model.bytes.empty())throw PartImportError("empty downloaded model: "+model.name);
        plan.files.push_back(model);
    }
    const auto metadata=part_metadata_json(p);
    const auto symbol=part_generate_symbol(p.safe_name,p.pins,info);
    const auto footprint=part_convert_footprint(result,p.safe_name,info,p.models_3d,ep);
    plan.files.push_back({p.safe_name+".kicad_sym",sexpr_dumps(symbol)+"\n"});
    plan.files.push_back({p.safe_name+".kicad_mod",sexpr_dumps(footprint.tree)+"\n"});
    plan.files.push_back({"part.json",metadata});
    // Keep the exact input response bytes as the replay cache. Reformatting a
    // generic JsonNode loses integer/float spelling and unknown future fields.
    plan.files.push_back({p.safe_name+".easyeda.json",response_json});
    plan.part=p;plan.pad_count=footprint.pad_count;plan.diagnostics=footprint.diagnostics;
    return plan;
}
} // namespace schgen
