#include "schgen/authoring.hpp"
#include "schgen/symbols.hpp"
#include "model_checks_internal.hpp"
#include <cctype>

namespace schgen {
namespace {
using model_checks::repr;
using model_checks::trim;
bool same(const CircuitPinRefIr& a, const CircuitPinRefIr& b) { return a.ref == b.ref && a.pin == b.pin; }
bool same(const CircuitPortIr& a, const CircuitPortIr& b) {
    return a.kind==b.kind && a.has_pair_with==b.has_pair_with && a.pair_with==b.pair_with &&
        a.has_impedance==b.has_impedance && a.impedance==b.impedance && a.has_role==b.has_role &&
        a.role==b.role && a.has_bus==b.has_bus && a.bus==b.bus && a.has_speed_hz==b.has_speed_hz &&
        a.speed_hz==b.speed_hz && a.has_level_v==b.has_level_v && a.level_v==b.level_v &&
        a.has_expect==b.has_expect && a.expect==b.expect;
}
std::string spec(const CircuitPinRefIr& p) { return p.ref+"."+p.pin; }
std::string footprint(const std::string& lib, const std::string& value) {
    if (lib=="Device:R") return "Resistor_SMD:R_0603_1608Metric";
    if (lib!="Device:C") return {};
    std::smatch m;
    double uf=0;
    if (std::regex_match(value,m,std::regex(R"(\s*([0-9.]+)\s*([pnu]?)F?\s*)"))) {
        std::size_t used=0;
        try { uf=std::stod(m[1], &used); }
        catch (const std::exception&) { throw CircuitAuthoringError("invalid capacitor value "+repr(value)); }
        if (used!=static_cast<std::size_t>(m[1].length())) throw CircuitAuthoringError("invalid capacitor value "+repr(value));
        if(m[2]=="p") uf*=1e-6;
        else if(m[2]=="n") uf*=1e-3;
    }
    return uf>=1 ? "Capacitor_SMD:C_0805_2012Metric" : "Capacitor_SMD:C_0603_1608Metric";
}
template<class T> auto by_net(T& entries, const std::string& net) {
    return std::find_if(entries.begin(),entries.end(),[&](const auto& x){return x.net==net;});
}
std::string repr_type(const CircuitPortIr& p) {
    const auto opt=[](bool has,const std::string& s){return has?repr(s):"None";};
    auto level=model_checks::fmt(p.level_v,17);
    if(level.find_first_of(".eE")==std::string::npos) level+=".0";
    return "PortType(kind="+repr(p.kind)+", pair_with="+opt(p.has_pair_with,p.pair_with)+
        ", impedance="+(p.has_impedance?std::to_string(p.impedance):"None")+
        ", role="+opt(p.has_role,p.role)+", bus="+opt(p.has_bus,p.bus)+
        ", speed_hz="+(p.has_speed_hz?std::to_string(p.speed_hz):"None")+
        ", level_v="+(p.has_level_v?level:"None")+", expect="+opt(p.has_expect,p.expect)+")";
}
}
AuthoringContext make_authoring_context(const std::filesystem::path& repository) {
    auto library=std::make_shared<SymbolLibrary>(repository);
    AuthoringContext context;
    context.pins=[library](const std::string& lib)->std::optional<std::set<std::string>> {
        try{return library->pin_numbers(lib);}catch(const SymbolError&){return std::nullopt;}
    };
    return context;
}
CircuitAuthor::CircuitAuthor(std::string name, std::string title, AuthoringContext context)
    :context_(std::move(context)) {
    circuit_.schema="schgen.circuit/1"; circuit_.name=std::move(name);
    circuit_.title=title.empty()?circuit_.name:std::move(title);
}
CircuitAuthor::CircuitAuthor(CircuitSheetIr circuit, AuthoringContext context)
    :circuit_(std::move(circuit)),context_(std::move(context)) {
    for(const auto& p:circuit_.parts) {
        std::smatch m;
        if(std::regex_match(p.ref,m,std::regex(R"(([A-Za-z]+[_A-Za-z]*)([0-9]+))")))
            counters_[m[1]]=std::max(counters_[m[1]],static_cast<std::size_t>(std::stoull(m[2])));
    }
}
CircuitSheetIr CircuitAuthor::finish() const {
    return parse_circuit_ir(authored_circuit_json(circuit_));
}
const CircuitNetIr* CircuitAuthor::find_net(const std::string& name) const {
    auto i=std::find_if(circuit_.nets.begin(),circuit_.nets.end(),[&](const auto& n){return n.name==name;});
    return i==circuit_.nets.end()?nullptr:&*i;
}
CircuitPartIr& CircuitAuthor::find_part(const std::string& ref) {
    auto i=std::find_if(circuit_.parts.begin(),circuit_.parts.end(),[&](const auto& p){return p.ref==ref;});
    if(i==circuit_.parts.end()) throw CircuitAuthoringError("unknown part "+repr(ref));
    return *i;
}
std::string CircuitAuthor::auto_ref(const std::string& prefix) {
    auto& n=counters_[prefix];
    std::string ref;
    do {
        if(n==std::numeric_limits<std::size_t>::max())throw CircuitAuthoringError("reference counter overflow for "+repr(prefix));
        ref=prefix+std::to_string(++n);
    }
    while(std::any_of(circuit_.parts.begin(),circuit_.parts.end(),[&](const auto& p){return p.ref==ref;}));
    return ref;
}
std::string CircuitAuthor::classify(const std::string& name) {
    for(const auto* p:{"GND","GNDA","GNDD","GNDPWR","AGND","DGND","PGND","VSS","CHASSIS_GND"})
        if(model_checks::starts(name,p)) return "ground";
    if(model_checks::starts(name,"+") || name=="VBUS" || model_checks::starts(name,"VDD") ||
       model_checks::starts(name,"VCC")) return "power";
    return "signal";
}
std::string CircuitAuthor::part(const std::string& ref,const std::string& lib,const std::string& value,
    const std::string& fp,const AuthoringStrings& fields) {
    if(std::any_of(circuit_.parts.begin(),circuit_.parts.end(),[&](const auto& p){return p.ref==ref;}))
        throw CircuitAuthoringError("duplicate reference "+repr(ref));
    CircuitPartIr p{ref,lib,value,fp.empty()?footprint(lib,value):fp,{},{},{}};
    for(const auto& [k,v]:fields) p.fields.push_back({k,v});
    circuit_.parts.push_back(std::move(p)); return ref;
}
std::string CircuitAuthor::use_part(const std::string& mpn,const AuthoringPartSelection& s) {
    auto safe=std::regex_replace(mpn,std::regex("[^A-Za-z0-9._-]+"),"_");
    auto first=safe.find_first_not_of('_'),last=safe.find_last_not_of('_');
    safe=first==std::string::npos?"":safe.substr(first,last-first+1);
    if(!context_.part) throw CircuitAuthoringError("use_part: no catalog resolver");
    auto rec=context_.part(safe);
    if(rec.safe_name!=safe) throw CircuitAuthoringError("use_part("+repr(mpn)+"): catalog safe_name does not match folder "+repr(safe));
    if(!s.ref && rec.prefix.empty()) throw CircuitAuthoringError("use_part("+repr(mpn)+"): catalog prefix is empty");
    const auto choose=[](const std::optional<std::string>& a,const std::string& b){return a&&!a->empty()?*a:b;};
    const auto ref=s.ref?*s.ref:auto_ref(rec.prefix);
    AuthoringStrings fields={{"LCSC",rec.lcsc.empty()?s.lcsc.value_or(""):rec.lcsc}};
    if(s.lib_id) {fields.emplace_back("MPN",rec.mpn);if(!rec.datasheet.empty()) fields.emplace_back("Datasheet",rec.datasheet);}
    part(ref,choose(s.lib_id,rec.lib_id),choose(s.value,rec.mpn),choose(s.footprint,rec.footprint),fields);
    if(!s.lib_id) {
        auto& p=find_part(ref);
        for(const auto& pin:rec.pins) {
            if(std::find(p.pin_numbers.begin(),p.pin_numbers.end(),pin.number)==p.pin_numbers.end())p.pin_numbers.push_back(pin.number);
            auto i=std::find_if(p.pin_names.begin(),p.pin_names.end(),[&](const auto& n){return n.name==pin.name;});
            if(i==p.pin_names.end())p.pin_names.push_back({pin.name,{pin.number}});else i->numbers.push_back(pin.number);
        }
    }
    return ref;
}
void CircuitAuthor::field(const std::string& ref,const std::string& key,const std::string& value) {
    auto& p=find_part(ref);
    for(auto& f:p.fields) if(f.key==key){f.value=value;return;}
    p.fields.push_back({key,value});
}
std::vector<CircuitPinRefIr> CircuitAuthor::expand_pin(const std::string& pin) const {
    const auto dot=pin.find('.');
    if(dot==std::string::npos || dot==0 || dot+1==pin.size())throw CircuitAuthoringError("bad pin spec "+repr(pin)+" (want 'REF.PIN')");
    const auto ref=pin.substr(0,dot),number=pin.substr(dot+1);
    auto i=std::find_if(circuit_.parts.begin(),circuit_.parts.end(),[&](const auto& p){return p.ref==ref;});
    if(i==circuit_.parts.end())throw CircuitAuthoringError(pin+": unknown part "+repr(ref));
    if(!i->pin_numbers.empty()) {
        if(std::find(i->pin_numbers.begin(),i->pin_numbers.end(),number)!=i->pin_numbers.end())return {{ref,number}};
        for(const auto& n:i->pin_names)if(n.name==number){std::vector<CircuitPinRefIr> out;for(const auto& num:n.numbers)out.push_back({ref,num});return out;}
        throw CircuitAuthoringError(pin+": "+i->value+" has no pin number or name "+repr(number));
    }
    if(context_.pins) {
        const auto nums=context_.pins(i->lib_id);
        if(nums&&!nums->count(number))throw CircuitAuthoringError(pin+": "+i->value+" ("+i->lib_id+") has no pin number "+repr(number));
    }
    return {{ref,number}};
}
CircuitPinRefIr CircuitAuthor::single_pin(const std::string& pin) const {
    auto pins=expand_pin(pin);
    if(pins.size()!=1)throw CircuitAuthoringError(pin+": names "+std::to_string(pins.size())+" stacked pins — this context needs exactly one");
    return pins.front();
}
std::optional<std::string> CircuitAuthor::net_of(const CircuitPinRefIr& pin) const {
    for(const auto& n:circuit_.nets)for(const auto& p:n.pins)if(same(p,pin))return n.name;
    return std::nullopt;
}
void CircuitAuthor::net(const std::string& name,const std::vector<std::string>& pins,const std::optional<std::string>& cls) {
    if(cls && *cls!="power" && *cls!="ground" && *cls!="port" && *cls!="signal")throw CircuitAuthoringError("unknown net class "+repr(*cls));
    auto i=std::find_if(circuit_.nets.begin(),circuit_.nets.end(),[&](const auto& n){return n.name==name;});
    if(i==circuit_.nets.end()){circuit_.nets.push_back({name,cls.value_or(classify(name)),{}});i=std::prev(circuit_.nets.end());}
    else if(cls && i->net_class!=*cls)throw CircuitAuthoringError("net "+repr(name)+" reclassified "+i->net_class+"->"+*cls);
    for(const auto& pin:pins)for(const auto& p:expand_pin(pin)) {
        if(std::any_of(circuit_.nc.begin(),circuit_.nc.end(),[&](const auto& x){return same(x,p);}))throw CircuitAuthoringError(spec(p)+" is declared NC but assigned to "+repr(name));
        const auto owner=net_of(p);
        if(owner&&*owner!=name)throw CircuitAuthoringError(spec(p)+" already on net "+repr(*owner)+", cannot also join "+repr(name));
        if(!owner)i->pins.push_back(p);
    }
}
void CircuitAuthor::port(const std::string& name,const std::vector<std::string>& pins,const AuthoringPort& type,bool explicit_type) {
    net(name,pins,"port");
    if(explicit_type || type.kind!="single" || type.pair_with || type.role || type.bus || type.expect || type.impedance || type.speed_hz || type.level_v)
        port_type(name,type);
}
void CircuitAuthor::port_type(const std::string& name,const AuthoringPort& type) {
    auto t=type;
    const auto prefix="port_type("+repr(name)+"): ";
    const std::set<std::string> kinds={"single","diff_pair","usb_hs_pair","tmds_pair","i2c","sd_bus"};
    if(!kinds.count(t.kind))throw CircuitAuthoringError(prefix+"unknown kind "+repr(t.kind));
    auto n=find_net(name);
    if(!n||n->net_class!="port")throw CircuitAuthoringError(prefix+"not a declared PORT net");
    const bool pair=t.kind=="diff_pair"||t.kind=="usb_hs_pair"||t.kind=="tmds_pair";
    if(pair) {
        if(!t.pair_with)throw CircuitAuthoringError(prefix+t.kind+" needs pair_with=");
        auto comp=find_net(*t.pair_with);
        if(!comp||comp->net_class!="port")throw CircuitAuthoringError(prefix+"pair_with "+repr(*t.pair_with)+" is not a declared PORT net");
        if(!t.impedance && t.kind=="usb_hs_pair")t.impedance=90;
        if(!t.impedance && t.kind=="tmds_pair")t.impedance=100;
        if(!t.impedance)throw CircuitAuthoringError(prefix+"diff_pair needs explicit impedance=");
    } else if(t.pair_with)throw CircuitAuthoringError(prefix+"pair_with only valid for pair kinds, not "+repr(t.kind));
    if(t.kind=="i2c") {
        if(t.role!="scl" && t.role!="sda")throw CircuitAuthoringError(prefix+"i2c needs role='scl' or 'sda'");
    } else if(t.role)throw CircuitAuthoringError(prefix+"role only valid for i2c");
    if(t.kind=="sd_bus"&&!t.level_v)throw CircuitAuthoringError(prefix+"sd_bus needs level_v=");
    CircuitPortIr p; p.net=name;p.kind=t.kind;
    p.has_pair_with=bool(t.pair_with);p.pair_with=t.pair_with.value_or("");
    p.has_impedance=bool(t.impedance);p.impedance=t.impedance.value_or(0);
    p.has_role=bool(t.role);p.role=t.role.value_or("");p.has_bus=bool(t.bus);p.bus=t.bus.value_or("");
    p.has_speed_hz=bool(t.speed_hz);p.speed_hz=t.speed_hz.value_or(0);
    p.has_level_v=bool(t.level_v);p.level_v=t.level_v.value_or(0);
    p.has_expect=bool(t.expect);p.expect=t.expect.value_or("");
    auto i=by_net(circuit_.port_types,name);
    if(i!=circuit_.port_types.end()&&!same(*i,p))throw CircuitAuthoringError(prefix+"retyped "+repr_type(*i)+" -> "+repr_type(p)+" (conflict)");
    if(i==circuit_.port_types.end())circuit_.port_types.push_back(p);
    if(pair) {
        auto reciprocal=p;reciprocal.net=*t.pair_with;reciprocal.pair_with=name;
        reciprocal.role="";reciprocal.has_role=false;reciprocal.speed_hz=0;reciprocal.has_speed_hz=false;reciprocal.level_v=0;reciprocal.has_level_v=false;
        auto c=by_net(circuit_.port_types,*t.pair_with);
        if(c==circuit_.port_types.end())circuit_.port_types.push_back(reciprocal);
        else if(!same(*c,reciprocal))throw CircuitAuthoringError(prefix+"complement "+repr(*t.pair_with)+" already typed "+repr_type(*c)+", conflicts with "+repr_type(reciprocal));
    }
}
void CircuitAuthor::nc(const std::vector<std::string>& pins) {
    for(const auto& pin:pins)for(const auto& p:expand_pin(pin)) {
        if(net_of(p))throw CircuitAuthoringError(spec(p)+" carries a net, cannot be NC");
        if(std::none_of(circuit_.nc.begin(),circuit_.nc.end(),[&](const auto& x){return same(x,p);}))circuit_.nc.push_back(p);
    }
}
CircuitPortIr CircuitAuthor::port_type_of(const std::string& net) const {
    auto i=by_net(circuit_.port_types,net);
    if(i!=circuit_.port_types.end())return *i;
    CircuitPortIr p;p.net=net;p.kind="single";return p;
}
CircuitSheetIr CircuitAuthor::subset(const std::set<std::string>& refs,int page) const {
    CircuitSheetIr out;out.schema=circuit_.schema;out.name=circuit_.name+"."+std::to_string(page);out.title=circuit_.title;
    for(const auto& ref:refs) {
        auto p=std::find_if(circuit_.parts.begin(),circuit_.parts.end(),[&](const auto& x){return x.ref==ref;});
        if(p==circuit_.parts.end())throw CircuitAuthoringError("unknown part "+repr(ref));
        out.parts.push_back(*p);
    }
    for(const auto& p:circuit_.nc)if(refs.count(p.ref))out.nc.push_back(p);
    std::set<std::string> nets;
    for(const auto& n:circuit_.nets) {
        auto kept=n;kept.pins.clear();
        for(const auto& p:n.pins)if(refs.count(p.ref))kept.pins.push_back(p);
        if(kept.pins.empty())continue;
        if(n.net_class=="signal"&&kept.pins.size()!=n.pins.size())
            throw CircuitAuthoringError("SIGNAL net "+repr(n.name)+" would be CUT across pages — OPEN");
        out.nets.push_back(kept);nets.insert(n.name);
        if(n.net_class=="port") {
            auto p=by_net(circuit_.port_types,n.name);if(p!=circuit_.port_types.end())out.port_types.push_back(*p);
        }
        auto h=by_net(circuit_.hints,n.name);if(h!=circuit_.hints.end())out.hints.push_back(*h);
    }
    for(const auto& l:circuit_.loads)if(nets.count(l.rail))out.loads.push_back(l);
    for(const auto& w:circuit_.waivers)if(refs.count(w.key.substr(0,w.key.find('.')))||nets.count(w.key))out.waivers.push_back(w);
    return out;
}
void CircuitAuthor::validate(const std::vector<std::pair<std::string,std::vector<std::string>>>& pins) const {
    std::vector<std::string> errors;
    std::set<std::pair<std::string,std::string>> assigned,nc;
    for(const auto& p:circuit_.nc)nc.emplace(p.ref,p.pin);
    for(const auto& n:circuit_.nets) {
        if(n.net_class=="signal"&&n.pins.size()<2)errors.push_back("net "+repr(n.name)+": single-pin internal signal net");
        for(const auto& p:n.pins) {
            assigned.emplace(p.ref,p.pin);
            const auto have=model_checks::find(pins,p.ref);
            if(have&&std::find(have->begin(),have->end(),p.pin)==have->end())errors.push_back(spec(p)+": pin does not exist on "+p.ref);
        }
    }
    for(const auto& [ref,numbers]:pins)for(const auto& number:numbers)
        if(!assigned.count({ref,number})&&!nc.count({ref,number}))errors.push_back(ref+"."+number+": UNASSIGNED (net it or declare nc())");
    if(!errors.empty()) {
        std::string out="circuit "+repr(circuit_.name)+" incomplete:";
        for(const auto& e:errors)out+="\n  "+e;
        throw CircuitAuthoringError(out);
    }
}
void CircuitAuthor::bind(const AuthoringStrings& mapping) {
    std::set<std::string> sources,targets;
    for(const auto& [from,to]:mapping) {
        auto n=find_net(from);
        if(!n)throw CircuitAuthoringError("bind: "+repr(from)+" is not a net on circuit "+repr(circuit_.name));
        if(n->net_class=="signal")throw CircuitAuthoringError("bind: "+repr(from)+" is a private SIGNAL net — only POWER/GROUND/PORT (rail/port) externals are bindable; a subsystem's internal wiring is never rebound");
        if(to.empty())throw CircuitAuthoringError("bind: target name must not be empty");
        if(!sources.insert(from).second)throw CircuitAuthoringError("bind: duplicate source "+repr(from));
        if(!targets.insert(to).second)throw CircuitAuthoringError("bind: distinct externals cannot merge onto one net (LAW-0 short)");
    }
    for(const auto& [from,to]:mapping)if(find_net(to)&&!sources.count(to)&&from!=to)
        throw CircuitAuthoringError("bind: "+repr(from)+" -> "+repr(to)+" collides with the existing net "+repr(to)+" on this circuit");
    const auto rename=[&](std::string& s){for(const auto& [a,b]:mapping)if(s==a){s=b;return;}};
    for(auto& n:circuit_.nets)rename(n.name);
    for(auto& p:circuit_.port_types){rename(p.net);if(p.has_pair_with)rename(p.pair_with);}
    for(auto& l:circuit_.loads)rename(l.rail);
    for(auto& h:circuit_.hints)rename(h.net);
    for(auto& w:circuit_.waivers)if(w.kind!="thermal_waivers"&&w.kind!="part_rule_waivers")rename(w.key);
    for(auto& p:circuit_.parts)if(p.lib_id=="Connector:TestPoint"||p.lib_id=="Mechanical:MountingHole_Pad")rename(p.value);
}
void CircuitAuthor::hint(const std::string& name,const std::string& style) {
    if(style!="trunk")throw CircuitAuthoringError("hint("+repr(name)+"): unknown style "+repr(style)+" (known: ['trunk'])");
    if(!find_net(name))throw CircuitAuthoringError("hint("+repr(name)+"): not a declared net");
    auto i=by_net(circuit_.hints,name);if(i!=circuit_.hints.end())i->style=style;else circuit_.hints.push_back({name,style});
}
void CircuitAuthor::draws(const std::string& rail,double amps,const std::string& note) {
    auto n=find_net(rail);const auto prefix="draws("+repr(rail)+"): ";
    if(!n)throw CircuitAuthoringError(prefix+"not a declared net");
    if(n->net_class!="power")throw CircuitAuthoringError(prefix+"not a POWER rail ("+n->net_class+")");
    if(!(amps>0))throw CircuitAuthoringError(prefix+"amps must be > 0");
    circuit_.loads.push_back({rail,amps,note});
}
void CircuitAuthor::waive(const std::string& kind,const std::string& key,const std::string& reason) {
    const std::set<std::string> kinds={"tp_waivers","decap_waivers","pull_waivers","reset_waivers","strap_waivers","ep_waivers","thermal_waivers","part_rule_waivers"};
    if(!kinds.count(kind))throw CircuitAuthoringError("unknown waiver kind "+repr(kind));
    const auto why=trim(reason);
    if(why.empty())throw CircuitAuthoringError(kind+"("+repr(key)+"): a reason is required");
    const auto ref=key.substr(0,key.find('.'));
    const bool have_ref=std::any_of(circuit_.parts.begin(),circuit_.parts.end(),[&](const auto& p){return p.ref==ref;});
    if(kind=="thermal_waivers"||kind=="part_rule_waivers") { (void)find_part(key); }
    else if(kind=="tp_waivers"||kind=="pull_waivers"||kind=="reset_waivers") {
        if(!find_net(key))throw CircuitAuthoringError(kind+"("+repr(key)+"): not a declared net");
    } else if(!have_ref&&!find_net(key))throw CircuitAuthoringError(kind+"("+repr(key)+"): not a part ref, 'ref.pin', or declared net");
    for(auto& w:circuit_.waivers)if(w.kind==kind&&w.key==key){w.reason=why;return;}
    circuit_.waivers.push_back({kind,key,why});
}
std::string CircuitAuthor::testpoint(const std::string& name,const std::optional<std::string>& ref) {
    const auto n=find_net(name);const auto prefix="testpoint("+repr(name)+"): ";
    if(!n)throw CircuitAuthoringError(prefix+"not a declared net");
    if(n->net_class=="signal")throw CircuitAuthoringError(prefix+"internal SIGNAL net — probe points cover rails and PORT buses (make it a port or waive)");
    if(n->pins.empty())throw CircuitAuthoringError(prefix+"net has no pins yet — declare the circuit first");
    const auto r=ref?*ref:auto_ref("TP");
    part(r,"Connector:TestPoint",name,"TestPoint:TestPoint_Pad_D1.5mm",{{"BOM","exclude"}});net(name,{r+".1"});return r;
}
std::string CircuitAuthor::mounting_hole(const std::string& name,const std::optional<std::string>& ref) {
    validate_mounting_hole_net(circuit_,name);
    const auto r=ref?*ref:auto_ref("H");return add_mounting_hole(circuit_,name,r).ref;
}
std::vector<std::string> CircuitAuthor::decouple(const std::string& pin,const std::vector<std::string>& values,
    const std::optional<std::string>& rail,const std::string& gnd,const std::string& lib,const std::string& fp) {
    auto p=single_pin(pin);auto r=rail&&!rail->empty()?rail:net_of(p);
    if(!r)throw CircuitAuthoringError("decouple("+spec(p)+"): rail unknown — net the pin first");
    std::vector<std::string> out;
    for(const auto& v:values){auto ref=auto_ref("C");part(ref,lib,v,fp);net(*r,{ref+".1"});net(gnd,{ref+".2"});out.push_back(ref);}return out;
}
std::string CircuitAuthor::pullup(const std::string& pin,const std::string& value,const std::string& rail,const std::string& lib,const std::string& fp) {
    const auto p=single_pin(pin);const auto sig=net_of(p);
    if(!sig)throw CircuitAuthoringError("pullup("+spec(p)+"): net the signal pin first");
    auto ref=auto_ref("R");part(ref,lib,value,fp);net(*sig,{ref+".2"});net(rail,{ref+".1"});return ref;
}
std::string CircuitAuthor::series(const std::string& in,const std::string& out,const std::string& value,const std::string& prefix,const std::string& lib,const std::string& fp) {
    auto ref=auto_ref(prefix);part(ref,lib,value,fp);net(in,{ref+".1"});net(out,{ref+".2"});return ref;
}
SubsystemMeta::SubsystemMeta(const JsonNode& value) {
    if(value.kind==JsonKind::Null)return;
    if(value.kind!=JsonKind::Object)throw CircuitAuthoringError("subsystem meta must be a dict");
    std::set<std::string> keys;
    for(const auto& [key,items]:value.object_value) {
        if(key!="bind"&&key!="expects"&&key!="buses"&&key!="notes")throw CircuitAuthoringError("unknown subsystem meta key(s) ["+repr(key)+"] — legal keys are ['bind', 'expects', 'buses', 'notes']");
        if(!keys.insert(key).second)throw CircuitAuthoringError("duplicate subsystem meta key "+repr(key));
        if(items.kind==JsonKind::Null)continue;
        if(items.kind!=JsonKind::Object)throw CircuitAuthoringError("subsystem meta["+repr(key)+"] must be a dict");
        std::set<std::string> seen;
        for(const auto& [k,v]:items.object_value) {
            if(!seen.insert(k).second)throw CircuitAuthoringError("duplicate subsystem meta item "+repr(k));
            if(v.kind!=JsonKind::String && !(key=="expects"&&v.kind==JsonKind::Null))throw CircuitAuthoringError("subsystem meta["+repr(key)+"]["+repr(k)+"] must be a string"+(key=="expects"?" or null":""));
            if(key=="expects")expects_.emplace_back(k,v.kind==JsonKind::Null?std::nullopt:std::optional<std::string>(v.string_value));
            else (key=="bind"?bind_:key=="buses"?buses_:notes_).emplace_back(k,v.string_value);
        }
    }
}
std::string SubsystemMeta::bus(const std::string& role,const std::string& fallback) const {auto v=model_checks::find(buses_,role);return v?*v:fallback;}
std::string SubsystemMeta::note(const std::string& key,const std::string& fallback) const {auto v=model_checks::find(notes_,key);return v?*v:fallback;}
std::optional<std::string> SubsystemMeta::expect(const std::string& port,std::optional<std::string> fallback) const {auto v=model_checks::find(expects_,port);return v?*v:fallback;}
std::optional<std::string> SubsystemMeta::expect_kw(const std::string& port) const {auto v=expect(port);return v&&!v->empty()?v:std::nullopt;}
CircuitSheetIr SubsystemMeta::finish(CircuitAuthor& c) const {c.bind(bind_);return c.finish();}
} // namespace schgen
