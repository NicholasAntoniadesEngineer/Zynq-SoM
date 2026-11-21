#include "schgen/part_checks.hpp"
#include "model_checks_internal.hpp"

#include <set>

namespace schgen {
using namespace model_checks;

namespace {
const char* const ratings_schema = "schgen.part_ratings/1";
const std::set<std::string> rating_row_keys{"lcsc", "kind", "v_max", "i_max", "p_max", "tol", "dielectric", "temp_max", "vin_max", "source"};

std::optional<double> rating_number(const JsonNode& row, const char* key, const std::string& where) {
    const JsonNode* value = object_field(row, key);
    if (!value) return std::nullopt;
    if (value->kind != JsonKind::Number || !std::isfinite(value->number_value))
        throw ModelCheckError(where + ": " + key + " must be a finite number");
    return value->number_value;
}

std::optional<std::string> rating_text(const JsonNode& row, const char* key, const std::string& where) {
    const JsonNode* value = object_field(row, key);
    if (!value) return std::nullopt;
    if (value->kind != JsonKind::String) throw ModelCheckError(where + ": " + key + " must be a string");
    return value->string_value;
}
}

PartRatingsTable parse_part_ratings(const JsonNode& root, const std::string& source) {
    const std::string file = "part ratings " + source;
    reject_unknown_keys(root, {"schema", "ratings"}, file);
    if (require_string(root, "schema", false, file) != ratings_schema)
        throw ModelCheckError(file + ": schema must be " + ratings_schema);
    const JsonNode* rows = object_field(root, "ratings");
    if (!rows || rows->kind != JsonKind::Array || rows->array_value.empty())
        throw ModelCheckError(file + ": ratings must be a non-empty array");
    PartRatingsTable table;
    std::set<std::string> seen;
    for (std::size_t index = 0; index < rows->array_value.size(); ++index) {
        const JsonNode& row = rows->array_value[index];
        const std::string where = file + " row " + std::to_string(index + 1);
        reject_unknown_keys(row, rating_row_keys, where);
        const std::string lcsc = require_string(row, "lcsc", false, where);
        if (!seen.insert(lcsc).second) throw ModelCheckError(where + ": lcsc " + lcsc + " is listed twice");
        PartRatings ratings;
        ratings.kind = require_string(row, "kind", false, where);
        ratings.source = require_string(row, "source", false, where);
        ratings.v_max = rating_number(row, "v_max", where);
        ratings.i_max = rating_number(row, "i_max", where);
        ratings.p_max = rating_number(row, "p_max", where);
        ratings.tol = rating_text(row, "tol", where);
        ratings.dielectric = rating_text(row, "dielectric", where);
        ratings.temp_max = rating_number(row, "temp_max", where);
        ratings.vin_max = rating_number(row, "vin_max", where);
        table.emplace_back(lcsc, std::move(ratings));
    }
    return table;
}

PartRatingsTable load_part_ratings(const std::filesystem::path& file) {
    if (!std::filesystem::is_regular_file(file))
        throw ModelCheckError("the part ratings file is missing: " + file.string());
    return parse_part_ratings(parse_json_file(file.string()), file.string());
}

std::filesystem::path part_ratings_file() { return SCHGEN_PART_RATINGS; }

const PartRatingsTable& default_part_ratings() {
    static const PartRatingsTable table = load_part_ratings(part_ratings_file());
    return table;
}

std::optional<PartRatings> part_ratings_from_json(const JsonNode& node) {
    if(node.kind!=JsonKind::Object)return {};
    auto kind=object_field(node,"kind");
    if(!kind||kind->kind==JsonKind::Null||(kind->kind==JsonKind::String&&kind->string_value.empty()))return {};
    if(kind->kind!=JsonKind::String)throw ModelCheckError("part ratings: kind must be a string");
    PartRatings r;r.kind=kind->string_value;
    auto number=[&](const char* name)->std::optional<double>{auto n=object_field(node,name);if(!n||n->kind==JsonKind::Null)return {};if(n->kind!=JsonKind::Number||!std::isfinite(n->number_value))throw ModelCheckError(std::string("part ratings: ")+name+" must be a finite number");return n->number_value;};
    auto str=[&](const char* name)->std::optional<std::string>{auto n=object_field(node,name);if(!n||n->kind==JsonKind::Null)return {};if(n->kind!=JsonKind::String)throw ModelCheckError(std::string("part ratings: ")+name+" must be a string");return n->string_value;};
    r.v_max=number("v_max");r.i_max=number("i_max");r.p_max=number("p_max");r.tol=str("tol");r.dielectric=str("dielectric");r.temp_max=number("temp_max");r.vin_max=number("vin_max");r.source=str("source").value_or("");return r;
}
const PartRatings* ratings_for_part(const CircuitPartIr& part,const PartRatingsTable& table) {return find(table,trim(field(part,"LCSC")));}

std::optional<double> parse_resistor_ohms(const std::string& value) {
    auto s=numeric_text(trim(value));replace_all(s,"Ω","");replace_all(s,"ohm","");
    static const std::regex infix(R"(^([0-9]+)([RrKkMm])([0-9]+)$)"),suffix(R"(^([0-9]+(?:\.[0-9]+)?)([RrKkMm]?)$)");
    auto mult=[](std::string s){s=upper(s);return s=="K"?1e3:s=="M"?1e-3:1.0;};
    std::smatch m;
    // Preserve the baseline's /10 fractional rule (4k70 is 11k) and M=milli.
    if(std::regex_match(s,m,infix))return (std::strtod(m[1].str().c_str(),nullptr)+std::strtod(m[3].str().c_str(),nullptr)/10)*mult(m[2]);
    if(std::regex_match(s,m,suffix))return std::strtod(m[1].str().c_str(),nullptr)*mult(m[2]);
    return {};
}
double capacitor_derating(const PartRatings& r,const PartRulePolicy& p) {
    auto d=upper(r.dielectric.value_or(""));if(d=="C0G"||d=="NP0")return p.derate_c0g;
    if(r.kind=="elec"||r.kind=="tant")return p.derate_elec;return p.derate_mlcc;
}
namespace {
std::vector<double> pin_volts(const CircuitSheetIr& c,const std::string& ref,const PowerPolicy& p) {
    std::vector<double> out;
    for(const auto& n:c.nets)if(std::any_of(n.pins.begin(),n.pins.end(),[&](const auto& pin){return pin.ref==ref;}))if(auto v=rail_volts(n.name,p))out.push_back(*v);
    return out;
}
const char* const voltage_quantity = part_check_voltage_quantity;
const char* const power_quantity = part_check_power_quantity;
const char* const reference_quantity = "reference_current_limit";
const char* const cap_rule = "CAP_V";
const char* const power_rule = "RES_POWER";
const char* const input_rule = "IC_VIN";
const char* const reference_suffix = "_REFERENCE";
const double input_voltage_limit = 1.0;
PartCheckVerdict part_finding(PartCheckResult& res,const std::string& key,const std::string& msg) {
    if(auto waiver=find(res.waived,key)){res.notes.push_back("WAIVED "+msg+" ["+waiver->second+"]");return PartCheckVerdict::waived;}
    res.findings.push_back(msg);return PartCheckVerdict::fail;
}
void record_check(PartCheckResult& res,const std::string& sheet,const std::string& ref,const std::string& rule,const char* quantity,PartCheckVerdict verdict,PartCheckBound bound,std::optional<double> stress,std::optional<double> rating,std::optional<double> ratio,std::optional<double> limit) {
    res.evaluated.push_back({sheet,ref,rule,quantity,verdict,bound,stress,rating,ratio,limit});
}
}
PartCheckResult analyze_part_rules(const std::vector<ProjectCircuit>& sheets,const PowerCheckResult& power,const PowerPolicy& power_policy,const PartRatingsTable& ratings,const PartRulePolicy& policy) {
    PartCheckResult res;res.waived=waivers(sheets,"part_rule_waivers");
    std::vector<const ProjectCircuit*> order;for(const auto& s:sheets)order.push_back(&s);
    std::stable_sort(order.begin(),order.end(),[](auto a,auto b){return a->name<b->name;});
    for(auto sc:order) {
        ModelSheetIndex idx(sc->circuit);
        for(const auto& [ref,part]:idx.parts) {
            // Catalog-specific pinout, independent of mutable display value or
            // alias metadata. SCPS113O 8.1.2/10: different supply nets must not
            // be bridged by the reference FET without current limiting. Equal
            // nominal voltages do not establish identical power sequencing.
            const auto* reference=part_fact(power_policy.reference_pins,catalogue_part_number(*part));
            if(reference) {
                const auto* v1=idx.net(ref,reference->vref1_pin);
                const auto* v2=idx.net(ref,reference->vref2_pin);
                if(v1&&v2&&v1->name!=v2->name) {
                    const auto rail=rail_volts(v2->name,power_policy);
                    if(rail&&*rail>0) {
                        ++res.checked;
                        record_check(res,sc->name,ref,reference->label+reference_suffix,reference_quantity,PartCheckVerdict::fail,PartCheckBound::none,std::nullopt,std::nullopt,std::nullopt,std::nullopt);
                        // No waiver: this is an observed direct connection,
                        // not a voltage-rating advisory or a transient model.
                        res.findings.push_back(reference->label+"_REFERENCE "+sc->name+":"+ref+
                            ": VREF2 directly on "+v2->name+" with VREF1 on "+v1->name+
                            "; missing reference current limiting (TI SCPS113O 8.1.2/10). "
                            "EN resistance does not limit this path; power sequencing remains unqualified.");
                    }
                }
            }
            auto r=ratings_for_part(*part,ratings);auto key=sc->name+":"+ref,lcsc=field(*part,"LCSC");
            if(!r){if(!trim(lcsc).empty())res.unspecced.push_back(key+" ("+part->value+", LCSC "+lcsc+") — no ratings row");continue;}
            if((r->kind=="mlcc"||r->kind=="elec"||r->kind=="tant"||r->kind=="film")&&r->v_max&&*r->v_max!=0) {
                auto vs=pin_volts(sc->circuit,ref,power_policy);
                if(vs.empty()){res.unspecced.push_back(key+" ("+part->value+") — cap rail unresolved");continue;}
                double rail=*std::max_element(vs.begin(),vs.end());if(rail<=0)continue;
                ++res.checked;double derate=capacitor_derating(*r,policy),need=derate*rail;
                PartCheckVerdict verdict=PartCheckVerdict::pass;
                if(*r->v_max<need)verdict=part_finding(res,key,"CAP_V "+key+" ("+part->value+", LCSC "+lcsc+"): "+g(*r->v_max)+"V "+(r->dielectric&&!r->dielectric->empty()?*r->dielectric:r->kind)+" on a "+g(rail)+"V rail — needs >= "+g(derate)+"x = "+g(need)+"V (margin "+f(*r->v_max/rail,1)+"x). Pick a higher-V part or c.waive_part_rule("+repr(ref)+", reason)");
                record_check(res,sc->name,ref,cap_rule,voltage_quantity,verdict,PartCheckBound::at_least,rail,*r->v_max,*r->v_max/rail,derate);
            } else if(r->kind=="res"&&r->p_max&&*r->p_max!=0) {
                auto ohms=parse_resistor_ohms(part->value);auto vs=pin_volts(sc->circuit,ref,power_policy);
                if(ohms&&*ohms>0&&vs.size()>=2) {
                    double dv=*std::max_element(vs.begin(),vs.end())-*std::min_element(vs.begin(),vs.end()),p=dv*dv / *ohms;
                    ++res.checked;
                    record_check(res,sc->name,ref,power_rule,power_quantity,p>policy.derate_res * *r->p_max?PartCheckVerdict::advisory:PartCheckVerdict::pass,PartCheckBound::at_most,p,*r->p_max,p/ *r->p_max,policy.derate_res);
                    if(p>policy.derate_res * *r->p_max)res.notes.push_back("RES_POWER(advisory) "+key+" ("+part->value+"): P~="+f(p*1000,0)+"mW across "+g(dv)+"V > "+g(policy.derate_res)+"x rated "+f(*r->p_max*1000,0)+"mW — verify it is not a full-rail dissipator");
                }
            }
        }
    }
    std::map<std::pair<std::string,std::string>,std::string> lcsc;
    for(const auto& s:sheets)for(const auto& p:s.circuit.parts)lcsc[{s.name,p.ref}]=trim(field(p,"LCSC"));
    for(auto r:sorted_regs(power)) {
        auto it=lcsc.find({r->sheet,r->ref});auto rating=find(ratings,it==lcsc.end()?std::string{}:it->second);
        auto key=r->sheet+":"+r->ref;
        if(!rating||!rating->vin_max){res.unspecced.push_back(key+" ("+r->value+") — no vin_max rating");continue;}
        auto v=rail_volts(r->vin,power_policy);
        if(!v){res.unspecced.push_back(key+" ("+r->value+") — input rail "+r->vin+" unresolved");continue;}
        ++res.checked;
        PartCheckVerdict verdict=PartCheckVerdict::pass;
        if(*rating->vin_max<*v)verdict=part_finding(res,key,"IC_VIN "+key+" ("+r->value+"): abs-max input "+g(*rating->vin_max)+"V < its rail "+r->vin+" "+g(*v)+"V — over-stress");
        record_check(res,r->sheet,r->ref,input_rule,voltage_quantity,verdict,PartCheckBound::at_least,*v,*rating->vin_max,*v>0?std::optional<double>(*rating->vin_max/ *v):std::nullopt,input_voltage_limit);
    }
    return res;
}
PartCheckResult analyze_part_rules(const std::vector<ProjectCircuit>& sheets,const PowerPolicy& power_policy,const PartRatingsTable& ratings,const PartRulePolicy& policy) {
    return analyze_part_rules(sheets,analyze_power(sheets,power_policy),power_policy,ratings,policy);
}
std::string part_rules_report(const PartCheckResult& res,const PartRulePolicy& p) {
    std::vector<std::string> ls{"schgen per-part rule engine (ratings vs netlist usage)",std::string(78,'='),"",
        "enforced: CAP_VOLTAGE (MLCC "+g(p.derate_mlcc)+"x / C0G "+g(p.derate_c0g)+"x / elec "+g(p.derate_elec)+"x rail), IC_VIN (abs-max >= input rail). advisory: RES_POWER ("+g(p.derate_res)+"x).",
        std::to_string(res.checked)+" part-checks evaluated; ratings from schgen/ratings.py (LCSC-keyed)."};
    if(!res.waived.empty()){ls.insert(ls.end(),{"","author waivers, verbatim ("+std::to_string(res.waived.size())+"):"});for(const auto& [k,v]:sorted(res.waived))ls.push_back("  "+pad(k,22)+" "+v.second);}
    auto section=[&](const std::vector<std::string>& entries,const std::string& heading,const std::string& prefix){auto rows=entries;std::sort(rows.begin(),rows.end());if(!rows.empty()){ls.insert(ls.end(),{"",heading+" ("+std::to_string(rows.size())+"):"});for(const auto& s:rows)ls.push_back(prefix+s);}};
    section(res.notes,"notes / advisory","  + ");section(res.unspecced,"UNSPEC — reported, NOT failing","  ? ");
    if(res.findings.empty())ls.insert(ls.end(),{"","errors: none"});else section(res.findings,"ERRORS","  ERROR: ");
    ls.insert(ls.end(),{"",std::string("PART RULES: ")+(res.ok()?"PASS":"FAIL")+" ("+std::to_string(res.checked)+" checks, "+std::to_string(res.findings.size())+" findings, "+std::to_string(res.unspecced.size())+" unspeced, "+std::to_string(res.waived.size())+" waived)"});return join(ls);
}
PartCheckResult run_part_checks(const std::vector<ProjectCircuit>& sheets,const std::filesystem::path& dir,const PowerPolicy& pp,const PowerCheckResult* power,const PartRatingsTable& ratings,const PartRulePolicy& policy) {
    auto res=power?analyze_part_rules(sheets,*power,pp,ratings,policy):analyze_part_rules(sheets,pp,ratings,policy);
    publish(dir/"part_rules.txt",part_rules_report(res,policy)+"\n");return res;
}
JsonNode part_result_json(const PartCheckResult& res) {
    return obj({{"findings",strings(res.findings)},{"notes",strings(res.notes)},{"unspecced",strings(res.unspecced)},{"waived",waiver_json(res.waived)},{"checked",j(double(res.checked))}});
}
JsonNode part_ratings_json(const PartRatings& r) {
    return obj({{"kind",j(r.kind)},{"v_max",opt(r.v_max)},{"i_max",opt(r.i_max)},{"p_max",opt(r.p_max)},{"tol",opt(r.tol)},{"dielectric",opt(r.dielectric)},{"temp_max",opt(r.temp_max)},{"vin_max",opt(r.vin_max)},{"source",j(r.source)}});
}

PartCheckResult part_result_from_json(const JsonNode& n) {
    object_shape(n,{"findings","notes","unspecced","waived","checked"},"part result");
    PartCheckResult r;r.findings=read_strings(member(n,"findings"));r.notes=read_strings(member(n,"notes"));r.unspecced=read_strings(member(n,"unspecced"));r.waived=read_waivers(member(n,"waived"));r.checked=count(member(n,"checked"));return r;
}

} // namespace schgen
