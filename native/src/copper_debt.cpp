#include "schgen/copper_debt.hpp"
#include "model_checks_internal.hpp"
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <sstream>

namespace schgen {
namespace {
using namespace model_checks;
const char* const claims_schema = "schgen.copper_claims/1";
const char* const claims_folder = "subsystems";
const char* const claims_file = "copper_claims.json";
const char* const unmeasured_emits = "UNMEASURED — no emitted board scanned";
const char* const unmeasured_status = "UNMEASURED";
const char* const unscanned_inventory = "NO BOARD SCANNED (statuses UNMEASURED)";
const char* const decimal_digits = "0123456789";
const char* const decimal_suffix = ".0";
const std::set<std::string> sheet_kinds{"part", "net_pins", "part_count", "thermal_fact", "part_fact"};
const std::map<std::string, std::set<std::string>> check_keys{
    {"part", {"kind", "scopes", "sheet", "refs", "all_parts", "lib_id", "footprint", "value_prefix", "fields", "pins"}},
    {"net_pins", {"kind", "scopes", "sheet", "net", "pins"}},
    {"part_count", {"kind", "scopes", "sheet", "count"}},
    {"thermal_fact", {"kind", "scopes", "sheet", "refs", "rth_ja", "rth_ja_pour", "pour_evidence"}},
    {"part_fact", {"kind", "scopes", "sheet", "refs", "section"}},
    {"thermal_credit", {"kind", "part", "need"}},
    {"emission_via", {"kind", "size_mm", "drill_mm"}},
    {"emission_ground_layer", {"kind", "layer"}},
    {"isolation_margins", {"kind"}},
    {"impedance_geometry", {"kind", "impedance_ohm"}}};
const std::set<std::string> fact_sections{"ep_vias", "isolation"};
struct MeasureSpec {
    std::set<std::string> plain;
    std::map<std::string, std::set<std::string>> templates;
};
const std::map<std::string, MeasureSpec> measure_specs{
    {"thermal_via_field", {{"part"}, {{"emits", {"plane", "rows"}}, {"row", {"ref", "count", "radius"}}, {"pour", {"layer", "state"}}}}},
    {"ep_via_pads", {{"part"}, {{"emits", {"plane", "rows"}}, {"row", {"ref", "count"}}}}},
    {"net_island", {{"net"}, {{"emits", {"zones", "vias"}}}}},
    {"plane_voids", {{"zone_prefix", "min_voids_with_plane", "none_text"}, {{"emits", {"names"}}}}},
    {"reference_plane", {{}, {{"emits", {"x0", "y0", "x1", "y1"}}, {"absent_emits", {}}}}},
    {"module_body_vias", {{"zone_prefix", "found_text", "missing_text"}, {{"emits", {"count", "zone"}}}}}};
const std::set<std::string> inventory_keys{"with_text", "without_text", "emits"};
const std::set<std::string> inventory_placeholders{"fills", "plane", "rules", "vias", "gnd", "segments"};
const std::set<std::string> plane_keys{"net", "layer"};
const std::set<std::string> top_keys{"schema", "plane", "inventory", "claims"};
const std::set<std::string> claim_keys{"id", "title", "assumes", "risk", "checks", "measure"};

bool starts(const std::string& s,const std::string& p) { return s.rfind(p,0)==0; }
[[noreturn]] void refuse(const std::string& where,const std::string& why) { throw CopperProvenanceError(where+": "+why); }
void claim(bool valid,const std::string& id,const std::string& why) {
    if(!valid) throw CopperProvenanceError("copper_debt "+id+": "+why);
}
std::string number(double n) { std::ostringstream o; o << std::setprecision(6) << n; return o.str(); }
std::string decimal(double n) { auto t=number(n); return t.find_first_not_of(decimal_digits)==std::string::npos ? t+decimal_suffix : t; }
std::string yes(bool b) { return b ? "YES" : "NO"; }
std::string status(bool all,bool partial) { return all ? "EMITTED" : (partial ? "PARTIAL" : "NOTHING"); }
const char* kind_name(JsonKind k) {
    switch(k) {
        case JsonKind::Null: return "null";
        case JsonKind::Bool: return "boolean";
        case JsonKind::Number: return "number";
        case JsonKind::String: return "string";
        case JsonKind::Array: return "array";
        case JsonKind::Object: return "object";
    }
    return "value";
}
const JsonNode* optional_member(const JsonNode& n,const std::string& key,JsonKind kind,const std::string& where) {
    const auto* v=object_field(n,key);
    if(v && v->kind!=kind) refuse(where,"field '"+key+"' must be a "+kind_name(kind));
    return v;
}
const JsonNode& member(const JsonNode& n,const std::string& key,JsonKind kind,const std::string& where) {
    const auto* v=optional_member(n,key,kind,where);
    if(!v) refuse(where,"missing required field '"+key+"'");
    return *v;
}
std::string text_of(const JsonNode& n,const std::string& key,const std::string& where) { return require_string(n,key,false,where); }
double number_of(const JsonNode& n,const std::string& key,const std::string& where) { return member(n,key,JsonKind::Number,where).number_value; }
int whole_of(const JsonNode& n,const std::string& key,const std::string& where) {
    const double v=number_of(n,key,where);
    if(v!=std::floor(v)) refuse(where,"field '"+key+"' must be a whole number");
    return static_cast<int>(v);
}
std::vector<std::string> texts_of(const JsonNode& n,const std::string& key,const std::string& where) {
    const auto& a=member(n,key,JsonKind::Array,where);
    if(a.array_value.empty()) refuse(where,"field '"+key+"' must not be empty");
    std::vector<std::string> out;
    for(const auto& e:a.array_value) {
        if(e.kind!=JsonKind::String || e.string_value.empty()) refuse(where,"field '"+key+"' must hold non-empty strings");
        out.push_back(e.string_value);
    }
    return out;
}
void validate_template(const std::string& t,const std::set<std::string>& allowed,const std::string& where) {
    for(std::size_t i=0;i<t.size();++i) {
        if(t[i]=='}') refuse(where,"template '"+t+"' has an unmatched closing brace");
        if(t[i]!='{') continue;
        const auto close=t.find('}',i);
        if(close==std::string::npos) refuse(where,"template '"+t+"' has an unterminated placeholder");
        const auto name=t.substr(i+1,close-i-1);
        if(!allowed.count(name)) refuse(where,"template '"+t+"' names the unknown placeholder '"+name+"'");
        i=close;
    }
}
std::string fill(const std::string& t,const std::map<std::string,std::string>& values) {
    std::string out;
    for(std::size_t i=0;i<t.size();++i) {
        if(t[i]!='{') { out+=t[i]; continue; }
        const auto close=t.find('}',i);
        const auto found=values.find(t.substr(i+1,close-i-1));
        if(found==values.end()) throw CopperProvenanceError("copper_debt: template '"+t+"' names a placeholder the measure does not supply");
        out+=found->second;
        i=close;
    }
    return out;
}
CopperCheck parse_check(const JsonNode& n,const std::string& base) {
    if(n.kind!=JsonKind::Object) refuse(base,"a check must be an object");
    CopperCheck k;
    k.kind=text_of(n,"kind",base);
    const auto spec=check_keys.find(k.kind);
    const auto where=base+" ("+k.kind+")";
    if(spec==check_keys.end()) refuse(base,"unknown check kind '"+k.kind+"'");
    reject_unknown_keys(n,spec->second,where);
    if(sheet_kinds.count(k.kind)) { k.scopes=texts_of(n,"scopes",where); k.sheet=text_of(n,"sheet",where); }
    if(k.kind=="part") {
        const auto* refs=optional_member(n,"refs",JsonKind::Array,where);
        const auto* all=optional_member(n,"all_parts",JsonKind::Bool,where);
        if(bool(refs)==bool(all)) refuse(where,"exactly one of 'refs' and 'all_parts' is required");
        if(refs) k.refs=texts_of(n,"refs",where);
        if(all) { if(!all->bool_value) refuse(where,"'all_parts' must be true when present"); k.all_parts=true; }
        if(object_field(n,"lib_id")) k.lib_id=text_of(n,"lib_id",where);
        if(object_field(n,"footprint")) k.footprint=text_of(n,"footprint",where);
        if(object_field(n,"value_prefix")) k.value_prefix=text_of(n,"value_prefix",where);
        if(const auto* fields=optional_member(n,"fields",JsonKind::Object,where)) {
            if(fields->object_value.empty()) refuse(where,"field 'fields' must not be empty");
            for(const auto& [key,value]:fields->object_value) {
                if(value.kind!=JsonKind::String) refuse(where,"fields value of '"+key+"' must be a string");
                k.fields.emplace_back(key,value.string_value);
            }
        }
        if(const auto* pins=optional_member(n,"pins",JsonKind::Array,where)) {
            if(pins->array_value.empty()) refuse(where,"field 'pins' must not be empty");
            for(const auto& p:pins->array_value) {
                if(p.kind!=JsonKind::Object) refuse(where,"a pins row must be an object");
                reject_unknown_keys(p,{"pin","net","net_prefix"},where+" pins row");
                CopperPinNet row;
                row.pin=text_of(p,"pin",where+" pins row");
                const bool has_net=object_field(p,"net")!=nullptr, has_prefix=object_field(p,"net_prefix")!=nullptr;
                if(has_net==has_prefix) refuse(where,"a pins row needs exactly one of 'net' and 'net_prefix'");
                row.net=has_net ? text_of(p,"net",where+" pins row") : "";
                row.net_prefix=has_prefix ? text_of(p,"net_prefix",where+" pins row") : "";
                k.pins.push_back(row);
            }
        }
        const bool asserts=k.lib_id||k.footprint||k.value_prefix||!k.fields.empty()||!k.pins.empty();
        if(k.all_parts && !asserts) refuse(where,"'all_parts' needs at least one of lib_id, footprint, value_prefix, fields, pins");
    } else if(k.kind=="net_pins") {
        k.net=text_of(n,"net",where);
        const auto& rows=member(n,"pins",JsonKind::Array,where);
        if(rows.array_value.empty()) refuse(where,"field 'pins' must not be empty");
        for(const auto& row:rows.array_value) {
            const bool pair=row.kind==JsonKind::Array && row.array_value.size()==2 && row.array_value[0].kind==JsonKind::String &&
                row.array_value[1].kind==JsonKind::String && !row.array_value[0].string_value.empty() && !row.array_value[1].string_value.empty();
            if(!pair) refuse(where,"a pins row must be [reference, pin]");
            k.net_pins.emplace_back(row.array_value[0].string_value,row.array_value[1].string_value);
        }
    } else if(k.kind=="part_count") {
        k.count=whole_of(n,"count",where);
    } else if(k.kind=="thermal_fact") {
        k.refs=texts_of(n,"refs",where);
        k.rth_ja=number_of(n,"rth_ja",where);
        const auto* pour=object_field(n,"rth_ja_pour");
        if(!pour) refuse(where,"missing required field 'rth_ja_pour'");
        if(pour->kind==JsonKind::Number) k.rth_ja_pour=pour->number_value;
        else if(pour->kind!=JsonKind::Null) refuse(where,"field 'rth_ja_pour' must be a number or null");
        k.pour_evidence=require_string(n,"pour_evidence",true,where);
    } else if(k.kind=="part_fact") {
        k.refs=texts_of(n,"refs",where);
        k.section=text_of(n,"section",where);
        if(!fact_sections.count(k.section)) refuse(where,"unknown fact section '"+k.section+"'");
    } else if(k.kind=="thermal_credit") {
        k.part=text_of(n,"part",where);
        const auto& need=member(n,"need",JsonKind::Object,where);
        reject_unknown_keys(need,{"min_vias","radius_mm","pour_layers"},where+" need");
        k.need.min_vias=whole_of(need,"min_vias",where+" need");
        k.need.radius_mm=number_of(need,"radius_mm",where+" need");
        k.need.pour_layers=texts_of(need,"pour_layers",where+" need");
    } else if(k.kind=="emission_via") {
        k.size_mm=number_of(n,"size_mm",where); k.drill_mm=number_of(n,"drill_mm",where);
    } else if(k.kind=="emission_ground_layer") {
        k.layer=text_of(n,"layer",where);
    } else if(k.kind=="impedance_geometry") {
        k.impedance=whole_of(n,"impedance_ohm",where);
    }
    return k;
}
CopperMeasure parse_measure(const JsonNode& n,const std::string& base) {
    if(n.kind!=JsonKind::Object) refuse(base,"a measure must be an object");
    CopperMeasure m;
    m.kind=text_of(n,"kind",base);
    const auto spec=measure_specs.find(m.kind);
    const auto where=base+" ("+m.kind+")";
    if(spec==measure_specs.end()) refuse(base,"unknown measure kind '"+m.kind+"'");
    std::set<std::string> keys=spec->second.plain;
    keys.insert("kind");
    for(const auto& t:spec->second.templates) keys.insert(t.first);
    reject_unknown_keys(n,keys,where);
    for(const auto& key:spec->second.plain) {
        if(key=="min_voids_with_plane") m.min_voids=whole_of(n,key,where);
        else m.text[key]=text_of(n,key,where);
    }
    for(const auto& [key,allowed]:spec->second.templates) {
        m.text[key]=text_of(n,key,where);
        validate_template(m.text[key],allowed,where+" field '"+key+"'");
    }
    return m;
}
const CircuitSheetIr& sheet(const CopperDebtSources& s,const std::string& scope,const std::string& name) {
    for(const auto& c:s.circuits) if(c.scope==scope && c.sheet==name) return c.circuit;
    throw CopperProvenanceError("copper_debt: missing live "+scope+"/"+name);
}
const CircuitPartIr& part(const CircuitSheetIr& s,const std::string& ref,const std::string& id) {
    for(const auto& p:s.parts) if(p.ref==ref) return p;
    throw CopperProvenanceError("copper_debt "+id+": missing component "+s.name+":"+ref);
}
std::string net_of(const CircuitSheetIr& s,const std::string& ref,const std::string& pin) {
    std::string found;
    for(const auto& n:s.nets) for(const auto& p:n.pins) if(p.ref==ref && p.pin==pin) {
        if(!found.empty()) throw CopperProvenanceError("copper_debt: duplicate pin "+ref+"."+pin);
        found=n.name;
    }
    return found;
}
std::vector<const CopperZoneEvidence*> zones(const ThermalCopper& c,const std::string& prefix) {
    std::vector<const CopperZoneEvidence*> out;
    for(const auto& z:c.zones) if(starts(z.name,prefix)) out.push_back(&z);
    std::sort(out.begin(),out.end(),[](const auto* a,const auto* b){return a->name<b->name;}); return out;
}
std::pair<std::size_t,std::size_t> net_copper(const ThermalCopper& c,const std::string& net) {
    std::size_t z=0,v=0;
    for(const auto& x:c.zones) if(!x.keepout && x.net_name.find(net)!=std::string::npos) ++z;
    for(const auto& x:c.vias) if(x.net_name.find(net)!=std::string::npos) ++v;
    return {z,v};
}
bool fill_on(const CopperZoneEvidence& z,const std::string& net,const std::string& layer) {
    return !z.keepout && z.filled && z.net_name==net && std::find(z.layers.begin(),z.layers.end(),layer)!=z.layers.end();
}
bool plane_present(const ThermalCopper& c,const CopperPlane& plane) {
    return std::any_of(c.zones.begin(),c.zones.end(),[&](const auto& z){return fill_on(z,plane.net,plane.layer);});
}
std::size_t vias_within(const ThermalCopper& c,const std::string& net,double x,double y,double radius) {
    return static_cast<std::size_t>(std::count_if(c.vias.begin(),c.vias.end(),
        [&](const auto& v){return v.net_name==net && std::hypot(v.x-x,v.y-y)<=radius;}));
}
template<class Map> const typename Map::mapped_type& row_of(const Map& rows,const std::string& key,const std::string& section,const std::string& id) {
    const auto found=rows.find(key);
    if(found==rows.end()) throw CopperProvenanceError("copper_debt "+id+": "+key+" has no "+section+" entry in the part facts");
    return found->second;
}
void verify_part(const std::string& id,const CopperCheck& k,const CircuitSheetIr& sh,const CircuitPartIr& p) {
    const auto at=sh.name+":"+p.ref;
    if(k.lib_id) claim(p.lib_id==*k.lib_id,id,at+" symbol differs from claim");
    if(k.footprint) claim(p.footprint==*k.footprint,id,at+" footprint differs from claim");
    if(k.value_prefix) claim(starts(p.value,*k.value_prefix),id,"live component identity differs from claim at "+at);
    for(const auto& required:k.fields) {
        const auto f=std::find_if(p.fields.begin(),p.fields.end(),[&](const auto& x){return x.key==required.first;});
        claim(f!=p.fields.end() && f->value==required.second,id,at+" field "+required.first+" differs from claim");
    }
    for(const auto& pin:k.pins) {
        const auto net=net_of(sh,p.ref,pin.pin);
        claim(pin.net.empty() ? (!net.empty() && starts(net,pin.net_prefix)) : net==pin.net,id,at+" pin "+pin.pin+" connectivity differs from claim");
    }
}
void verify_sheet_check(const CopperDebtSources& sources,const std::string& id,const CopperCheck& k) {
    for(const auto& scope:k.scopes) {
        claim(sources.basis_scopes.count(scope)==1,id,"scope "+scope+" is neither the library nor a board folder");
        const auto& sh=sheet(sources,scope,k.sheet);
        if(k.kind=="part_count") { claim(static_cast<int>(sh.parts.size())==k.count,id,scope+"/"+k.sheet+" membership changed"); continue; }
        if(k.kind=="net_pins") {
            for(const auto& [ref,pin] : k.net_pins) {
                (void)part(sh,ref,id);
                claim(net_of(sh,ref,pin)==k.net,id,scope+"/"+k.sheet+" pin "+ref+"."+pin+" is not on "+k.net);
            }
            continue;
        }
        std::vector<std::string> refs=k.refs;
        if(k.all_parts) { refs.clear(); for(const auto& p:sh.parts) refs.push_back(p.ref); }
        for(const auto& ref:refs) {
            const auto& p=part(sh,ref,id);
            if(k.kind=="part") verify_part(id,k,sh,p);
            else if(k.kind=="thermal_fact") {
                const auto* spec=thermal_spec_for(p,sources.thermal);
                claim(spec && spec->rth_ja==k.rth_ja && spec->rth_ja_pour==k.rth_ja_pour &&
                    spec->pour_evidence==k.pour_evidence && !spec->cite.empty(),id,"live thermal policy differs from claim");
            } else if(k.section=="ep_vias")
                claim(ep_via_for(sources.ep_vias,sources.regulators,p.value)!=nullptr,id,"exposed-pad via requirement missing from the part data");
            else
                claim(part_fact_for(sources.emission.isolation,p.value,p.footprint)!=nullptr,id,"live component omitted by isolation policy");
        }
    }
}
void verify_thermal_credit(const CopperDebtSources& s,const std::string& id,const CopperCheck& k) {
    const auto& mpn=k.part;
    const auto& want=k.need;
    const auto& spec=row_of(s.thermal.specs,mpn,"thermal",id);
    claim(spec.rth_ja_pour && !spec.pour_evidence.empty(),id,"thermal policy of "+mpn+" grants no pour credit");
    const auto& need=row_of(s.emission.thermal_copper,mpn,"thermal_copper",id).need;
    claim(need.min_vias==want.min_vias && need.radius_mm==want.radius_mm && need.pour_layers==want.pour_layers,id,"thermal copper need of "+mpn+" differs from claim");
    const auto& label=row_of(s.regulators,mpn,"regulators",id).label;
    const auto n=std::find_if(s.thermal.pour_needs.begin(),s.thermal.pour_needs.end(),[&](const auto& x){return x.first==spec.pour_evidence;});
    claim(n!=s.thermal.pour_needs.end() && n->second.value_prefix==label && n->second.min_vias==want.min_vias &&
        n->second.radius_mm==want.radius_mm && n->second.pour_layers==want.pour_layers,id,"thermal evidence requirement differs from claim");
    const auto e=std::find_if(s.emission.thermal_credit_needs.begin(),s.emission.thermal_credit_needs.end(),
        [&](const auto& x){return x.value_prefix==label;});
    claim(e!=s.emission.thermal_credit_needs.end() && e->min_vias==want.min_vias &&
        e->radius_mm==want.radius_mm && e->pour_layers==want.pour_layers,id,"emitter and thermal evidence policies disagree with claim");
    const auto* c=thermal_field_for(s.emission.thermal_copper,s.emission.regulators,label);
    claim(c && c->max_vias>=want.min_vias && c->pour_layers==want.pour_layers && !c->cite.empty(),id,"thermal copper emission intent missing");
}
void verify_check(const CopperDebtSources& s,const std::string& id,const CopperCheck& k) {
    if(sheet_kinds.count(k.kind)) verify_sheet_check(s,id,k);
    else if(k.kind=="thermal_credit") verify_thermal_credit(s,id,k);
    else if(k.kind=="emission_via") claim(s.emission.thermal_via_size==k.size_mm && s.emission.thermal_via_drill==k.drill_mm,id,"thermal via geometry differs from claim");
    else if(k.kind=="emission_ground_layer") claim(s.emission.ground_layer==k.layer,id,"isolation/reference-layer policy differs from claim");
    else if(k.kind=="isolation_margins") claim(!s.emission.isolation.empty() &&
        std::all_of(s.emission.isolation.begin(),s.emission.isolation.end(),[](const auto& row){return row.second.margin_mm>0;}),id,"isolation/reference-layer policy differs from claim");
    else {
        const auto g=std::find_if(s.geometry.begin(),s.geometry.end(),[&](const auto& x){return x.impedance==k.impedance;});
        const auto* live=differential_geometry(k.impedance);
        claim(g!=s.geometry.end() && live && board_stackup().ground_referenced(false) && g->width_mm==live->width_mm &&
            g->gap_mm==live->gap_mm && g->source==live->source && !g->source.empty(),id,"live researched impedance geometry differs from claim");
    }
}
void verify_sources(const CopperDebtSources& s) {
    const auto audited = audit_component_basis(s.circuits,s.basis_scopes,s.basis);
    claim(audited.ok(),"basis",component_basis_report(audited));
    for(const auto& c:s.claims.claims) for(const auto& k:c.checks) verify_check(s,c.id,k);
}
std::vector<CopperDebtEntry> entries(const CopperClaims& claims) {
    std::vector<CopperDebtEntry> out;
    for(const auto& c:claims.claims)
        out.push_back({c.id,c.title,c.assumes,{claims.reference+"#"+c.id},unmeasured_emits,unmeasured_status,c.risk});
    return out;
}
std::string instance_rows(const std::vector<std::string>& rows) {
    std::string out;
    for(const auto& r:rows) { if(!out.empty()) out+="; "; out+=r; }
    return out;
}
void measure_instances(CopperDebtEntry& e,const CopperMeasure& m,const ThermalCopper& c,const CopperDebtSources& s,bool plane) {
    const bool field=m.kind=="thermal_via_field";
    const auto& label=row_of(s.regulators,m.text.at("part"),"regulators",e.eid).label;
    const auto found=c.instances(label);
    bool all=!found.empty() && plane, partial=plane;
    std::vector<std::string> rows;
    for(const auto* f:found) {
        if(field) {
            const auto& need=row_of(s.emission.thermal_copper,m.text.at("part"),"thermal_copper",e.eid).need;
            const auto n=vias_within(c,s.claims.plane.net,f->x,f->y,need.radius_mm);
            std::string pours;
            bool poured=true;
            for(const auto& layer:need.pour_layers) {
                const bool on=c.pour_at(f->x,f->y,layer,s.claims.plane.net);
                poured=poured && on;
                pours+=fill(m.text.at("pour"),{{"layer",layer},{"state",yes(on)}});
            }
            all=all && n>=static_cast<std::size_t>(need.min_vias) && poured;
            partial=partial || n!=0;
            rows.push_back(fill(m.text.at("row"),{{"ref",f->ref},{"count",std::to_string(n)},{"radius",decimal(need.radius_mm)}})+pours);
        } else {
            const auto* ep=ep_via_for(s.ep_vias,s.regulators,f->value);
            if(!ep) throw CopperProvenanceError("copper debt: "+f->value+" has no ep_vias entry in the part facts");
            std::size_t n=0;
            for(const auto& p:f->pads) if(p.drill>0 && p.net_name==s.claims.plane.net && std::hypot(p.dx,p.dy)<=ep->radius_mm) ++n;
            all=all && n>=static_cast<std::size_t>(ep->min_pads); partial=true;
            rows.push_back(fill(m.text.at("row"),{{"ref",f->ref},{"count",std::to_string(n)}}));
        }
    }
    e.emits=fill(m.text.at("emits"),{{"plane",yes(plane)},{"rows",instance_rows(rows)}});
    e.status=status(all,partial);
}
void measure_entry(CopperDebtEntry& e,const CopperMeasure& m,const ThermalCopper& c,const CopperDebtSources& s,bool plane) {
    const auto& plane_net=s.claims.plane.net;
    if(m.kind=="thermal_via_field" || m.kind=="ep_via_pads") { measure_instances(e,m,c,s,plane); return; }
    if(m.kind=="net_island") {
        const auto [z,v]=net_copper(c,m.text.at("net"));
        e.emits=fill(m.text.at("emits"),{{"zones",std::to_string(z)},{"vias",std::to_string(v)}});
        e.status=status(z!=0 && v!=0,z!=0 || v!=0);
    } else if(m.kind=="plane_voids") {
        const auto voids=zones(c,m.text.at("zone_prefix"));
        std::string names;
        for(const auto* z:voids) { if(!names.empty()) names+=", "; names+=z->name; }
        e.emits=fill(m.text.at("emits"),{{"names",names.empty()?m.text.at("none_text"):names}});
        e.status=(!plane ? !voids.empty() : voids.size()>=static_cast<std::size_t>(m.min_voids)) ? "PARTIAL" : "NOTHING";
    } else if(m.kind=="reference_plane") {
        e.status="NOTHING"; e.emits=m.text.at("absent_emits");
        for(const auto& z:c.zones) if(fill_on(z,plane_net,s.claims.plane.layer)) {
            e.status="EMITTED";
            e.emits=fill(m.text.at("emits"),{{"x0",number(z.bbox[0])},{"y0",number(z.bbox[1])},{"x1",number(z.bbox[2])},{"y1",number(z.bbox[3])}});
            break;
        }
    } else {
        const auto body=zones(c,m.text.at("zone_prefix")); std::size_t n=0;
        if(!body.empty()) for(const auto& v:c.vias) if(v.net_name==plane_net &&
            body[0]->bbox[0]<=v.x && v.x<=body[0]->bbox[2] && body[0]->bbox[1]<=v.y && v.y<=body[0]->bbox[3]) ++n;
        e.emits=fill(m.text.at("emits"),{{"count",std::to_string(n)},{"zone",body.empty()?m.text.at("missing_text"):m.text.at("found_text")}});
        e.status=n?"PARTIAL":"NOTHING";
    }
}
} // namespace
CopperClaims parse_copper_claims(const JsonNode& root,const std::string& file) {
    try {
        CopperClaims out;
        out.reference=std::string(claims_folder)+"/"+claims_file;
        if(root.kind!=JsonKind::Object) refuse(file,"the document must be an object");
        reject_unknown_keys(root,top_keys,file);
        if(require_string(root,"schema",false,file)!=claims_schema) refuse(file,std::string("schema must be ")+claims_schema);
        const auto& plane=member(root,"plane",JsonKind::Object,file);
        reject_unknown_keys(plane,plane_keys,file+" plane");
        out.plane.net=text_of(plane,"net",file+" plane"); out.plane.layer=text_of(plane,"layer",file+" plane");
        const auto& inventory=member(root,"inventory",JsonKind::Object,file);
        reject_unknown_keys(inventory,inventory_keys,file+" inventory");
        out.inventory_with=text_of(inventory,"with_text",file+" inventory");
        out.inventory_without=text_of(inventory,"without_text",file+" inventory");
        out.inventory_emits=text_of(inventory,"emits",file+" inventory");
        validate_template(out.inventory_emits,inventory_placeholders,file+" inventory field 'emits'");
        const auto& rows=member(root,"claims",JsonKind::Array,file);
        if(rows.array_value.empty()) refuse(file,"field 'claims' must not be empty");
        std::set<std::string> ids;
        for(std::size_t i=0;i<rows.array_value.size();++i) {
            const auto& row=rows.array_value[i];
            const auto row_where=file+" claims row "+std::to_string(i+1);
            if(row.kind!=JsonKind::Object) refuse(row_where,"a claim must be an object");
            CopperClaim c;
            c.id=text_of(row,"id",row_where);
            const auto where=file+" claim "+c.id;
            reject_unknown_keys(row,claim_keys,where);
            if(!ids.insert(c.id).second) refuse(where,"the id is used twice");
            c.title=text_of(row,"title",where); c.assumes=text_of(row,"assumes",where); c.risk=text_of(row,"risk",where);
            const auto& checks=member(row,"checks",JsonKind::Array,where);
            if(checks.array_value.empty()) refuse(where,"a claim needs at least one check");
            for(std::size_t j=0;j<checks.array_value.size();++j) c.checks.push_back(parse_check(checks.array_value[j],where+" check "+std::to_string(j+1)));
            c.measure=parse_measure(member(row,"measure",JsonKind::Object,where),where+" measure");
            out.claims.push_back(std::move(c));
        }
        return out;
    } catch(const CopperProvenanceError&) {
        throw;
    } catch(const std::runtime_error& e) {
        throw CopperProvenanceError(e.what());
    }
}
CopperClaims load_copper_claims(const std::filesystem::path& repository) {
    const auto path=repository/claims_folder/claims_file;
    if(!std::filesystem::is_regular_file(path)) throw CopperProvenanceError("the copper claims file is missing: "+path.string());
    return parse_copper_claims(parse_json_file(path.string()),path.string());
}
CopperDebtSources author_copper_debt_sources(const std::filesystem::path& repository) {
    CopperDebtSources s;
    s.claims=load_copper_claims(repository);
    s.basis=load_component_basis_policy(repository); s.basis_scopes=component_basis_scopes(repository);
    s.circuits=author_component_basis_inputs(repository,s.basis);
    s.thermal=default_thermal_policy(); s.emission=default_pcb_emit_policy();
    const PartFacts facts=load_part_facts_in(repository/"parts");
    s.emission.isolation=facts.isolation; s.emission.thermal_copper=facts.thermal_copper; s.emission.regulators=facts.regulators;
    s.regulators=facts.regulators; s.ep_vias=facts.ep_vias;
    std::set<int> seen;
    for(const auto& c:s.claims.claims) for(const auto& k:c.checks) if(k.kind=="impedance_geometry" && seen.insert(k.impedance).second) {
        const auto* g=differential_geometry(k.impedance);
        if(!g) throw CopperProvenanceError("missing native differential geometry");
        s.geometry.push_back(*g);
    }
    return s;
}
CopperDebtResult analyze_copper_debt(const ThermalCopper* c,const CopperDebtSources& s) {
    verify_sources(s);
    CopperDebtResult result{entries(s.claims),unscanned_inventory};
    if(!c) return result;
    std::size_t fills=0,rules=0,on_plane_net=0;
    for(const auto& z:c->zones) { if(!z.keepout && z.filled) ++fills; if(z.keepout) ++rules; }
    for(const auto& v:c->vias) if(v.net_name==s.claims.plane.net) ++on_plane_net;
    const bool plane=plane_present(*c,s.claims.plane);
    result.inventory=fill(s.claims.inventory_emits,{{"fills",std::to_string(fills)},{"plane",plane?s.claims.inventory_with:s.claims.inventory_without},
        {"rules",std::to_string(rules)},{"vias",std::to_string(c->vias.size())},{"gnd",std::to_string(on_plane_net)},{"segments",std::to_string(c->segments)}});
    for(std::size_t i=0;i<s.claims.claims.size();++i) measure_entry(result.entries[i],s.claims.claims[i].measure,*c,s,plane);
    return result;
}
std::string copper_debt_report(const CopperDebtResult& r) {
    std::ostringstream o;
    o << "schgen copper-debt ledger — copper-predicated claims vs the EMITTED board\n"
      << std::string(78,'=') << "\n\n"
      << "Engineering claims verified against live native circuits and policies, then\n"
      << "measured against emitted board copper. REPORT-ONLY copper debt; thermal\n"
      << "credits remain HARD-gated. 'where' identifies native claim metadata; missing\n"
      << "components, connections or inconsistent policies FAIL provenance verification.\n\n"
      << "emitted copper inventory: " << r.inventory << "\n\n";
    std::map<std::string,std::size_t> counts;
    for(const auto& e:r.entries) {
        ++counts[e.status];
        o << e.eid << "  " << e.title << "   [" << e.status << "]\n  assumes: " << e.assumes << "\n";
        for(std::size_t i=0;i<e.where.size();++i) o << (i==0?"  where:   ":"           ") << e.where[i] << "\n";
        o << "  emits:   " << e.emits << "\n  risk:    " << e.risk << "\n\n";
    }
    o << "COPPER DEBT: " << r.entries.size() << " entries — " << counts["EMITTED"]
      << " emitted, " << counts["PARTIAL"] << " partial, " << counts["NOTHING"]
      << " unemitted, " << counts["UNMEASURED"] << " unmeasured (report-only)";
    return o.str();
}
JsonNode copper_debt_result_json(const CopperDebtResult& r) {
    auto es=arr();
    for(const auto& e:r.entries) es.array_value.push_back(obj({{"eid",j(e.eid)},{"title",j(e.title)},
        {"assumes",j(e.assumes)},{"where",strings(e.where)},{"emits",j(e.emits)},{"status",j(e.status)},{"risk",j(e.risk)}}));
    return obj({{"entries",es},{"inventory",j(r.inventory)}});
}
CopperDebtResult copper_debt_result_from_json(const JsonNode& r) {
    CopperDebtResult out; out.inventory=require_string(r,"inventory",true,"copper debt");
    const auto* es=object_field(r,"entries");
    if(!es || es->kind!=JsonKind::Array) throw CopperProvenanceError("copper debt: entries must be array");
    for(const auto& e:es->array_value) {
        const auto get=[&](const char* key){return require_string(e,key,true,"copper debt entry");};
        CopperDebtEntry d; d.eid=get("eid"); d.title=get("title"); d.assumes=get("assumes");
        d.emits=get("emits"); d.status=get("status"); d.risk=get("risk");
        const auto* ws=object_field(e,"where");
        if(!ws || ws->kind!=JsonKind::Array) throw CopperProvenanceError("copper debt: where must be array");
        for(const auto& w:ws->array_value) {
            if(w.kind!=JsonKind::String) throw CopperProvenanceError("copper debt: where must contain strings");
            d.where.push_back(w.string_value);
        }
        out.entries.push_back(std::move(d));
    }
    return out;
}
} // namespace schgen
