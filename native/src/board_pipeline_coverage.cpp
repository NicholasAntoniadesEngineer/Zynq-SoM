#include "board_pipeline_internal.hpp"
#include "pcb_placement_gates_internal.hpp"
#include "gallery_diagram_internal.hpp"
#include "bringup_unicode.hpp"
#include "verification_internal.hpp"

namespace schgen {
namespace {
using namespace placement_gates;
std::string representation(const JsonNode& n){
    switch(n.kind){
    case JsonKind::Null:return "None";
    case JsonKind::Bool:return n.bool_value?"True":"False";
    case JsonKind::String:return repr(n.string_value);
    case JsonKind::Number:return board_pipeline_detail::json(n);
    case JsonKind::Array:{std::vector<std::string> items;for(const auto& v:n.array_value)items.push_back(representation(v));return "["+board_pipeline_detail::join(items)+"]";}
    case JsonKind::Object:{std::vector<std::string> items;for(const auto& [k,v]:n.object_value)items.push_back(repr(k)+": "+representation(v));return "{"+board_pipeline_detail::join(items)+"}";}
    }
    throw ProjectError("invalid coverage value");
}
// Regex [A-Za-z_+#]+ followed by Unicode decimal digits; compare arbitrary
// integers as normalized decimal strings, without overflowing a machine int.
auto ref_key(const std::string& ref){
    const auto cp=document_detail::codepoints(ref);std::size_t k=0;
    while(k<cp.size()&&((cp[k]>='A'&&cp[k]<='Z')||(cp[k]>='a'&&cp[k]<='z')||cp[k]=='_'||cp[k]=='+'||cp[k]=='#'))++k;
    if(!k)return std::make_tuple(ref,std::size_t{1},std::string("0"),ref);
    const auto prefix=ref.substr(0,k);std::string digits;
    for(;k<cp.size();++k){const auto d=bringup_detail::decimal_digit(cp[k]);if(d<0)break;digits+=static_cast<char>('0'+d);}
    const auto first=digits.find_first_not_of('0');digits=first==digits.npos?"0":digits.substr(first);
    return std::make_tuple(prefix,digits.size(),digits,ref);
}
std::vector<std::string> sorted_refs(const std::set<std::string>& refs){std::vector<std::string> out(refs.begin(),refs.end());std::sort(out.begin(),out.end(),[](const auto& a,const auto& b){return ref_key(a)<ref_key(b);});return out;}
std::set<std::string> structured_refs(const JsonNode& contract){
    std::set<std::string> out;const auto& roles=opt(contract,"roles");
    if(truth(roles)){kind(roles,JsonKind::Object);for(const auto& [name,value]:roles.object_value){(void)value;out.insert(name);}}
    for(const auto& st:array(opt(contract,"structures"))){kind(st,JsonKind::Object);
        for(const auto* key:{"ic","anchor","cap","resistor","inductor","cin","cout","own_inductor","foreign_ic","foreign_inductor"}){const auto& value=opt(st,key);if(value.kind==JsonKind::String)out.insert(value.string_value);}
        for(const auto* key:{"caps","members","ics"})for(const auto& v:array(opt(st,key)))out.insert(jstr(v));
        for(const auto& v:array(opt(st,"min_from")))if(v.kind==JsonKind::Object){const auto& p=opt(v,"part");if(p.kind==JsonKind::String)out.insert(p.string_value);}
    }
    return out;
}
}
BoardCoverageLintResult check_board_contract_coverage(const std::vector<CircuitSheetIr>& sheets,
        const std::map<std::string,JsonNode>& contracts,
        const std::map<std::string,std::map<std::string,std::string>>& ref_maps,bool enforce){
    using namespace placement_gates;using board_pipeline_detail::join;
    BoardCoverageLintResult out;std::map<std::string,std::vector<std::string>> lines;
    for(const auto& sheet:sheets){if(lines.count(sheet.name))throw ProjectError("duplicate coverage sheet: "+sheet.name);
        const auto ci=contracts.find(sheet.name);const JsonNode nil;const auto& contract=ci==contracts.end()?nil:ci->second;
        const auto structured=structured_refs(contract);std::vector<std::string> notes,detail;
        std::map<std::string,std::string> free;std::set<std::string> names,free_names,used;
        std::map<std::string,const CircuitPartIr*> parts;
        for(const auto& part:sheet.parts){if(!parts.emplace(part.ref,&part).second)throw ProjectError("duplicate coverage part: "+part.ref);names.insert(part.ref);}
        for(const auto& entry:array(opt(contract,"free"))){const auto* ref=entry.kind==JsonKind::Object?object_field(entry,"ref"):nullptr;
            if(!ref||ref->kind!=JsonKind::String){notes.push_back("free entry "+representation(entry)+" is not {'ref','why'}");continue;}
            const auto& v=opt(entry,"why");const auto why=verification::strip(!truth(v)?"":v.kind==JsonKind::String?v.string_value:representation(v));
            if(why.empty())notes.push_back("free "+ref->string_value+": missing 'why'");free[ref->string_value]=why;free_names.insert(ref->string_value);}
        for(const auto& ref:sorted_refs(free_names)){if(!names.count(ref))notes.push_back("free "+repr(ref)+" names no part on this sheet");
            else if(structured.count(ref))notes.push_back("free "+repr(ref)+" is already STRUCTURED (redundant)");else used.insert(ref);}
        std::map<std::string,std::set<std::string>> nets;for(const auto& net:sheet.nets)for(const auto& pin:net.pins)nets[pin.ref].insert(net.name);
        std::size_t nstructured=0,nungated=0;
        for(const auto& ref:sorted_refs(names)){if(structured.count(ref)){++nstructured;continue;}if(used.count(ref))continue;++nungated;
            const auto& ns=nets[ref];std::vector<std::string> shown;for(const auto& n:ns){if(shown.size()==6)break;shown.push_back(n);}std::string net_text=shown.empty()?"-":join(shown);
            if(ns.size()>6)net_text+=" (+"+std::to_string(ns.size()-6)+" more)";
            const auto mapping=ref_maps.find(sheet.name);std::string board="?";if(mapping!=ref_maps.end()){const auto it=mapping->second.find(ref);if(it!=mapping->second.end())board=it->second;}
            const auto& value=parts.at(ref)->value;detail.push_back("    UNGATED "+pad(ref,6)+" -> "+pad(board,8)+" "+pad(value.empty()?"?":value,22)+" nets: "+net_text);}
        for(const auto& ref:sorted_refs(used))detail.push_back("    FREE    "+pad(ref,6)+" — "+free.at(ref));
        std::sort(notes.begin(),notes.end());for(const auto& note:notes)detail.push_back("    NOTE    "+note);
        detail.insert(detail.begin(),pad(sheet.name,20)+" parts="+pad(std::to_string(parts.size()),3,true)+"  structured="+pad(std::to_string(nstructured),3,true)+"  free="+pad(std::to_string(used.size()),2,true)+"  UNGATED="+pad(std::to_string(nungated),3,true)+(contract.kind==JsonKind::Null?"  (no contract)":""));
        lines.emplace(sheet.name,std::move(detail));++out.sheets;out.parts+=parts.size();out.structured+=nstructured;out.free+=used.size();out.ungated+=nungated;
    }
    out.report="CONTRACT COVERAGE LINT — every wired-sheet part in >=1 contract structure or explicitly free\nCONTRACT COVERAGE LINT ("+std::string(enforce?"HARD":"advisory")+"): "+std::to_string(out.sheets)+" sheets, "+std::to_string(out.parts)+" parts — "+std::to_string(out.structured)+" structured / "+std::to_string(out.free)+" free / "+std::to_string(out.ungated)+" UNGATED\n";
    for(const auto& [name,ls]:lines){(void)name;out.report+='\n'+join(ls,"\n");}return out;
}
}
