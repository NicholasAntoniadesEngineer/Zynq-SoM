#include "schgen/symbol_law.hpp"
#include "verification_internal.hpp"

namespace schgen {
using namespace verification;
bool symbol_is_power_flag(const SchematicSymbolResolver& resolve,const std::string& id) {
    const SymbolDef* symbol;
    try {symbol=&resolve(id);}catch(const SymbolError&){return false;}
    const auto* children=std::get_if<SexprList>(&symbol->raw.v);if(!children)return false;
    for(const auto& child:*children) {
        const auto* list=std::get_if<SexprList>(&child.v);if(!list||list->empty())continue;
        if(const auto* tag=std::get_if<Sexpr::Sym>(&list->front().v)){if(tag->name=="power")return true;}
        else if(const auto* tag=std::get_if<std::string>(&list->front().v)){if(*tag=="power")return true;}
    }return false;
}
SymbolLawResult check_symbol_law(const std::vector<CircuitSheetIr>& circuits,const SchematicSymbolResolver& resolve,const std::map<std::string,std::string>& pending) {
    SymbolLawResult out;std::set<std::string> seen;
    for(const auto& c:circuits)for(const auto* part:ordered_parts(c)) {
        const auto& id=part->lib_id;if(!starts(id,"schgen:")||symbol_is_power_flag(resolve,id))continue;
        const auto found=pending.find(id);
        if(found!=pending.end()){if(seen.insert(id).second)out.pending.push_back(id+" ("+c.name+"."+part->ref+") — "+found->second);continue;}
        out.violations.push_back(c.name+"."+part->ref+" uses hand-built schgen-local real-part symbol "+repr(id)+
            " — migrate to a parts/<MPN>/ dossier (use_part WITHOUT lib_id=) or a stock KiCad symbol; schgen.kicad_sym may hold only (power) rail flags.");
    }
    return out;
}
SymbolLawResult check_symbol_law(const std::vector<CircuitSheetIr>& c,SymbolLibrary& l,const std::map<std::string,std::string>& p){return check_symbol_law(c,[&](const auto& id)->const SymbolDef&{return l.get(id);},p);}
std::string SymbolLawResult::summary() const {
    std::vector<std::string> out{"SYMBOL-LAW GATE: "+std::string(ok()?"PASS":"FAIL")+" (0 hand-built real-part symbols on the board"+
        (pending.empty()?"":"; "+std::to_string(pending.size())+" tracked-pending")+")"};
    for(const auto& v:violations)out.push_back("  VIOLATION: "+v);for(const auto& v:pending)out.push_back("  pending (tracked exception): "+v);return join(out);
}
JsonNode symbol_law_result_json(const SymbolLawResult& r){return obj({{"violations",strings(r.violations)},{"pending",strings(r.pending)},{"ok",j(r.ok())},{"summary",j(r.summary())}});}
}  // namespace schgen
