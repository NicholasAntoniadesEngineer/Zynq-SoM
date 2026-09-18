#include "schgen/bom_values.hpp"
#include "verification_internal.hpp"

namespace schgen {
using namespace verification;
std::optional<NormalizedBomValue> normalize_bom_value(const std::string& value,const std::optional<std::string>& hint) {
    auto s=strip(value);if(s.empty())return std::nullopt;auto cls=hint;
    auto low=s;for(char& c:low)if(c>='A'&&c<='Z')c=char(c-'A'+'a');
    if(ends(low,"ohm")){cls="R";s.resize(s.size()-3);}
    else if(ends(s,"Ω")){cls="R";s.resize(s.size()-2);}
    else if(ends(s,"F")){cls="C";s.pop_back();}
    else if(ends(s,"H")){cls="L";s.pop_back();}
    else if(ends(s,"R")||ends(s,"r")) {
        static const std::regex suffix(R"([0-9.]+(?:[pnumkKMG]|µ)?[Rr])");
        if(std::regex_match(s,suffix)){cls="R";s.pop_back();}
    }
    if(!cls)return std::nullopt;
    s=regex_numbers(strip(s));std::smatch m;
    static const std::map<std::string,double> prefix{{"",1},{"p",1e-12},{"n",1e-9},{"u",1e-6},{"µ",1e-6},{"m",1e-3},{"k",1e3},{"K",1e3},{"M",1e6},{"G",1e9}};
    static const std::regex embedded(R"(([0-9]+)([pnumkKMG]|µ)([0-9]+))");
    static const std::regex ordinary(R"(([0-9]+(?:\.[0-9]+)?)\s*([pnumkKMG]|µ)?)");
    if(std::regex_match(s,m,embedded))return NormalizedBomValue{*cls,std::strtod((m[1].str()+"."+m[3].str()).c_str(),nullptr)*prefix.at(m[2])};
    if(!std::regex_match(s,m,ordinary))return std::nullopt;
    return NormalizedBomValue{*cls,std::strtod(m[1].str().c_str(),nullptr)*prefix.at(m[2])};
}
bool equal_bom_values(const NormalizedBomValue& a,const NormalizedBomValue& b) {
    if(a.component_class!=b.component_class)return false;
    const auto hi=std::max(std::abs(a.magnitude),std::abs(b.magnitude));
    return hi==0||std::abs(a.magnitude-b.magnitude)<=0.005*hi;
}
BomValueCatalog bom_value_catalog_from_json(const JsonNode& node) {
    if(node.kind!=JsonKind::Object)throw std::invalid_argument("BOM value catalog must be an object");
    BomValueCatalog out;for(const auto& [code,row]:node.object_value) {
        if(row.kind!=JsonKind::Object)throw std::invalid_argument("BOM catalog entry must be an object: "+code);
        auto& entry=out[code];if(const auto* v=object_field(row,"value")){entry.value=*v;entry.has_value=true;}
        if(const auto* note=object_field(row,"note"))entry.note=*note;
    }
    return out;
}
BomValueCatalog load_bom_value_catalog(const std::filesystem::path& path){return bom_value_catalog_from_json(parse_json_file(path.string()));}
BomValueResult check_bom_values(const std::vector<ProjectCircuit>& sheets,const BomValueCatalog& catalog) {
    BomValueResult out;out.catalog_size=catalog.size();
    for(const auto& sheet:sheets)for(const auto& part:sheet.circuit.parts) {
        const auto lcsc=field(part,"LCSC");if(lcsc.empty())continue;
        const auto found=catalog.find(lcsc);
        if(found==catalog.end()){out.unverified.push_back(sheet.name+":"+part.ref+" "+repr(part.value)+" LCSC "+lcsc+" (not in catalog)");continue;}
        std::optional<std::string> hint;
        if(part.lib_id=="Device:R")hint="R";else if(part.lib_id=="Device:C")hint="C";else if(part.lib_id=="Device:L")hint="L";
        if(!hint)continue;const auto& entry=found->second;
        const auto declared=normalize_bom_value(part.value,hint);
        const auto actual=normalize_bom_value(entry.has_value?py_json_str(entry.value):"");
        if(!declared||!actual)continue;++out.checked;
        if(equal_bom_values(*declared,*actual))continue;
        out.ok=false;out.mismatches.push_back(sheet.name+":"+part.ref+" declares "+repr(part.value)+" but LCSC "+lcsc+
            " is "+py_json_repr(entry.value)+" ("+g(declared->magnitude)+" vs "+g(actual->magnitude)+" "+declared->component_class+")"+
            (truth(entry.note)?" — "+py_json_str(entry.note):""));
    }
    return out;
}
std::string BomValueResult::report() const {
    std::vector<std::string> lines{"bom value gate (LCSC actual value == declared value)",std::string(60,'='),
        "catalog: "+std::to_string(catalog_size)+" LCSC codes; "+std::to_string(checked)+" inline-passive checks"};
    if(mismatches.empty())lines.push_back("mismatches: none");
    else {lines.push_back("");lines.push_back("MISMATCH ("+std::to_string(mismatches.size())+") — FAIL:");for(const auto& v:mismatches)lines.push_back("  "+v);}
    if(!unverified.empty()) {lines.push_back("");lines.push_back("UNVERIFIED — reported, NOT failing ("+std::to_string(unverified.size())+"):");for(const auto& v:std::set<std::string>(unverified.begin(),unverified.end()))lines.push_back("  "+v);}
    return join(lines);
}
BomValueResult run_bom_values(const std::vector<ProjectCircuit>& sheets,const BomValueCatalog& catalog,const std::filesystem::path& dir) {
    auto out=check_bom_values(sheets,catalog);write_report(dir/"bom_values.txt",out.report());return out;
}
JsonNode bom_value_result_json(const BomValueResult& r) {return obj({{"ok",j(r.ok)},{"checked",j(double(r.checked))},{"mismatches",strings(r.mismatches)},{"unverified",strings(r.unverified)},{"catalog_size",j(double(r.catalog_size))},{"report",j(r.report())}});}
}  // namespace schgen
