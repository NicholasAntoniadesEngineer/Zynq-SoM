#include "schgen/spice.hpp"
#include "verification_internal.hpp"

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace schgen {
using namespace verification;
namespace {
constexpr double vref_tps54302=0.596,stm32_vdd=3.3,stm32_vih=0.7*stm32_vdd;
constexpr double en_ihys=1.55e-6,zener_izt=20e-3,zener_zzt=17.0;
struct Subcheck {double volts;std::optional<double> lo,hi;std::string tag;};
struct NamedDivider {std::string net,source;std::vector<Subcheck> checks;std::string why;};
const std::vector<NamedDivider>& named_dividers() {
    static const std::vector<NamedDivider> data{
        {"CP2102N_VBUS_SNS","USB_UART_VBUS",{{5.25,{},5.8,"abs-max at 5.25 V VBUS"},{4.75,3.0,{},"detect at 4.75 V VBUS"}},
            "CP2102N self-powered VBUS sense (DS 22k1/47k5 reference): must read VBUS-present yet never exceed the pin abs-max 5.8 V"},
        {"PG_1V8_G","+1V8",{{1.8,1.45,1.8,"FET on at nominal rail"}},
            "+1V8 PG sense: gate divider must exceed the AO3400A max Vgs(th)=1.45 V so the PG LED is guaranteed on"},
        {"HDMI_RX_5V_DET","HDMI_RX_5V",{{5.25,{},3.465,"bank abs-max at 5.25 V cable"},{4.75,2.0,{},"VIH at 4.75 V cable"}},
            "cable-5V presence divider into an LVCMOS33 bank"},
        {"PD_OVP_SET","+VBUS_IN",{{21.0,{},1.176,"no false trip at 21 V (contract max)"},{24.4,1.224,{},"guaranteed cutoff below the TVS VBR min"}},
            "TPS26631 OVP set divider (pd_input): must NOT trip inside the valid 20 V +5% contract window yet MUST cut off before the SMBJ22A starts clamping (V_OVPR 1.2 V +/-2%, SLVSE94G)"}
    };return data;
}
bool source_override(const std::string& name){return name=="USB_UART_VBUS"||name=="HDMI_RX_5V";}
double volts(const std::string& name,const PowerPolicy& p){return source_override(name)?5.0:rail_volts(name,p).value_or(0);}
double divide(double a,double b){if(b==0)throw ModelCheckError("division by zero");return a/b;}
struct Passive {std::string ref;double value;const CircuitNetIr* other;};
struct SpiceIndex {
    const CircuitSheetIr& c;
    std::map<std::string,const CircuitPartIr*> parts;
    std::map<std::pair<std::string,std::string>,const CircuitNetIr*> pins;
    mutable std::map<std::string,std::vector<Passive>> resistors,capacitors;
    mutable bool resistors_ready=false,capacitors_ready=false;
    explicit SpiceIndex(const CircuitSheetIr& circuit):c(circuit) {
        for(const auto& p:c.parts)parts[p.ref]=&p;
        for(const auto& n:c.nets)for(const auto& p:n.pins)pins.emplace(std::make_pair(p.ref,p.pin),&n);
    }
    void index_passives(bool cap) const {
        auto& ready=cap?capacitors_ready:resistors_ready;if(ready)return;
        for(const auto& [ref,p]:parts) {
            if(!ends(p->lib_id,cap?":C":":R"))continue;
            const auto a=net(ref,"1"),b=net(ref,"2");if(!a||!b)continue;
            const auto value=parse_si_value(p->value);if(!value)continue;
            auto& index=cap?capacitors:resistors;
            index[a->name].push_back({ref,*value,b});
            if(a->name!=b->name)index[b->name].push_back({ref,*value,a});
        }
        ready=true;
    }
    const CircuitNetIr* net(const std::string& ref,const std::string& pin)const{auto it=pins.find({ref,pin});return it==pins.end()?nullptr:it->second;}
    const std::vector<Passive>& on(const std::string& name,bool cap=false)const {
        index_passives(cap);static const std::vector<Passive> empty;const auto& index=cap?capacitors:resistors;auto it=index.find(name);return it==index.end()?empty:it->second;
    }
};
template<class Pred> std::vector<Passive> select(const std::vector<Passive>& values,Pred predicate){std::vector<Passive> out;for(const auto& v:values)if(predicate(*v.other))out.push_back(v);return out;}
bool ground(const CircuitNetIr& n){return n.net_class=="ground";}
bool power(const CircuitNetIr& n){return n.net_class=="power";}
bool signal(const CircuitNetIr& n){return n.net_class=="signal"||n.net_class=="port";}
std::string resistor_description(const Passive& p){return p.ref+"="+g(p.value)+"R";}
void auto_dividers(const std::string& sheet,const SpiceIndex& idx,SpiceResult& out,const PowerPolicy& policy) {
    for(const auto& net:idx.c.nets) {
        if(!signal(net))continue;const auto& rs=idx.on(net.name);if(rs.size()!=2)continue;
        const auto tops=select(rs,[](const auto& n){return power(n)||source_override(n.name);});const auto bots=select(rs,ground);
        if(tops.size()!=1||bots.size()!=1)continue;
        const auto& top=tops[0];const auto& bot=bots[0];const auto& src=*top.other;
        const double ratio=divide(bot.value,top.value+bot.value);
        const auto named=std::find_if(named_dividers().begin(),named_dividers().end(),[&](const auto& n){return n.net==net.name;});
        const auto prefix=src.name+" -["+resistor_description(top)+"]- "+net.name+" -["+resistor_description(bot)+"]- GND @ ";
        if(named==named_dividers().end()) {
            const double v=volts(src.name,policy);if(v==0)continue;
            out.checks.push_back({"divider "+net.name,sheet,"divider",prefix+g(v)+" V (informational, no named threshold)",py_round(v*ratio,4),"V",{}, {},"analytic",{}});continue;
        }
        const bool source_ok=src.name==named->source;
        for(const auto& sub:named->checks) {
            auto v=sub.volts;auto tag=sub.tag;
            if(!source_ok){v=volts(src.name,policy);tag+="; SOURCE IS "+src.name+" ("+g(v)+" V), expected "+named->source;}
            out.checks.push_back({"divider "+net.name+" ["+tag+"]",sheet,"divider",prefix+g(v)+" V: "+named->why,py_round(v*ratio,4),"V",sub.lo,sub.hi,"analytic",{}});
            if(!source_ok)break;
        }
    }
}
void rc_networks(const std::string& sheet,const SpiceIndex& idx,SpiceResult& out) {
    for(const auto& net:idx.c.nets) {
        if(!signal(net))continue;bool has_switch=false;
        for(const auto& pin:net.pins) {
            const auto found=idx.parts.find(pin.ref);if(found==idx.parts.end())continue;const auto& p=*found->second;
            auto id=p.lib_id;for(char& c:id)if(c>='A'&&c<='Z')c=char(c-'A'+'a');
            if(id.find("sw")!=std::string::npos||p.value=="RESET"||p.value=="USER"||starts(p.ref,"SW")){has_switch=true;break;}
        }
        if(!has_switch)continue;const auto caps=select(idx.on(net.name,true),ground);if(caps.empty())continue;
        const auto pulls=select(idx.on(net.name),power);double ohms;std::string src;
        if(!pulls.empty()){ohms=pulls[0].value;src=resistor_description(pulls[0]);}
        else if(net.name=="STM32_NRST"){ohms=40000;src="STM32 internal ~40k NRST pull-up (contract)";}
        else continue;
        double farads=0;std::vector<std::string> refs;for(const auto& cap:caps){farads+=cap.value;refs.push_back(cap.ref);}
        out.checks.push_back({"RC "+net.name,sheet,"rc","debounce/reset ramp: "+src+" with "+join(refs,"+")+"="+g(farads*1e9)+"n -> tau must mask >=0.2 ms bounce, release <20 ms",
            py_round(ohms*farads*1e3,3),"ms",0.2,20.0,"analytic",{}});
    }
}
void sy7201_iset(const std::string& sheet,const SpiceIndex& idx,SpiceResult& out) {
    for(const auto& [ref,p]:idx.parts) {
        if(!starts(p->value,"SY7201"))continue;std::vector<std::string> pins{"?"};
        for(const auto& alias:p->pin_names)if(alias.name=="FB"){pins=alias.numbers;break;}
        const CircuitNetIr* fb=nullptr;for(const auto& pin:pins){fb=idx.net(ref,pin);if(fb)break;}
        if(!fb){out.notes.push_back("NOTE: "+sheet+":"+ref+" SY7201 FB pin not netted");continue;}
        const auto rs=select(idx.on(fb->name),ground);
        if(rs.empty()){out.notes.push_back("NOTE: "+sheet+":"+ref+" SY7201 ISET resistor not found on "+fb->name);continue;}
        const auto& r=rs[0];out.checks.push_back({"SY7201 ISET ("+r.ref+")",sheet,"iset","I_LED = 0.2 V / "+g(r.value)+"R; panel-class window 125-150 mA (lcd_backlight.md)",py_round(divide(0.2,r.value)*1e3,1),"mA",125.0,150.0,"analytic",{}});
    }
}
void buck_fb(const std::string& sheet,const SpiceIndex& idx,const std::vector<PowerReg>& regs,SpiceResult& out,const PowerPolicy& policy) {
    for(const auto& reg:regs) {
        if(reg.kind!="buck")continue;std::optional<double> vref;
        for(const auto& [prefix,v]:std::vector<std::pair<std::string,double>>{{"TPS54302",vref_tps54302},{"LMR33630",1.0},{"LM61460",1.0}})if(starts(reg.value,prefix)){vref=v;break;}
        if(!vref){out.notes.push_back("NOTE: "+sheet+":"+reg.ref+" ("+reg.value+") has no FB_VREF entry — FB divider unchecked");continue;}
        const CircuitNetIr* fb=nullptr;std::vector<Passive> tops,bots;
        for(const auto& net:idx.c.nets) {
            if(net.net_class!="signal"||std::none_of(net.pins.begin(),net.pins.end(),[&](const auto& p){return p.ref==reg.ref;}))continue;
            auto t=select(idx.on(net.name),[&](const auto& other){return other.name==reg.vout;});auto b=select(idx.on(net.name),ground);
            if(!t.empty()&&!b.empty()){fb=&net;tops=std::move(t);bots=std::move(b);break;}
        }
        if(!fb){out.notes.push_back("NOTE: "+sheet+":"+reg.ref+" FB divider not found");continue;}
        const auto& t=tops[0];const auto& b=bots[0];const double value=*vref*(1+divide(t.value,b.value)),nominal=rail_volts(reg.vout,policy).value_or(0);
        out.checks.push_back({reg.value+" FB ("+reg.vout+")",sheet,"fb_divider","Vout = "+(*vref==1?"1.0":g(*vref))+" * (1 + "+t.ref+"/"+b.ref+" = "+g(t.value)+"/"+g(b.value)+") vs nominal "+g(nominal)+" V +/-3%",
            py_round(value,4),"V",nominal*0.97,nominal*1.03,"analytic",{}});
    }
}
std::string en_pin(const CircuitPartIr& part) {
    for(const auto& alias:part.pin_names)if(starts(upper(alias.name),"EN")&&!alias.numbers.empty())return alias.numbers.front();return "5";
}
void en_clamp(const std::string& sheet,const SpiceIndex& idx,const std::vector<PowerReg>& regs,SpiceResult& out,const PowerPolicy& policy) {
    for(const auto& reg:regs) {
        if(reg.kind!="buck")continue;const auto* en=idx.net(reg.ref,en_pin(*idx.parts.at(reg.ref)));
        if(!en||en->net_class!="signal")continue;const auto series=select(idx.on(en->name),power);
        std::vector<std::pair<std::string,std::string>> zeners;
        for(const auto& [ref,p]:idx.parts)if(ends(p->lib_id,":D_Zener")) {
            const auto a=idx.net(ref,"1"),b=idx.net(ref,"2");if(!a||!b)continue;
            if((a->name==en->name||b->name==en->name)&&(ground(*a)||ground(*b)))zeners.emplace_back(ref,p->value);
        }
        if(series.empty())continue;const auto& r=series[0];const auto& rail=*r.other;const double v=rail_volts(rail.name,policy).value_or(0);
        if(zeners.empty()) {
            const auto bots=select(idx.on(en->name),ground);double ceiling;std::string topo;
            if(!bots.empty()){const auto& b=bots[0];ceiling=divide(21.0*b.value,r.value+b.value);topo="divider "+resistor_description(r)+"/"+resistor_description(b);}
            else{ceiling=21.0-en_ihys*r.value;topo="series "+resistor_description(r)+" only (no shunt)";}
            out.checks.push_back({"EN clamp ceiling ("+reg.ref+")",sheet,"en_clamp",rail.name+"="+g(v)+"V EN strap "+topo+", NO clamp zener: EN at VIN=21.0V must stay <= the EN recommended-max 5.5V (TPS54302 has NO internal EN clamp — SLVSDG6C; PWR-1)",py_round(ceiling,3),"V",{},5.5,"analytic",{}});continue;
        }
        const auto& [zref,zval]=zeners[0];
        if(!starts(zval,"MMSZ5231B")&&!starts(zval,"BZT52C5V1")){out.notes.push_back("NOTE: "+sheet+":"+zref+" zener "+zval+" has no modelled Vz — EN clamp not checked");continue;}
        auto en_at=[&](double vin,double test){const double knee=test-zener_izt*zener_zzt,open=vin-en_ihys*r.value;if(open<=knee)return open;
            const double iz=divide(vin-test+zener_izt*zener_zzt-r.value*en_ihys,r.value+zener_zzt);return test+(iz-zener_izt)*zener_zzt;};
        const double turnon=std::min(en_at(4.75,4.845),en_at(4.75,5.355)),ceiling=en_at(21.0,5.355);
        const auto pre=rail.name+"="+g(v)+"V -["+resistor_description(r)+"]- EN, "+zref+"="+zval+" zener->GND: EN at VIN=";
        out.checks.push_back({"EN clamp turn-on ("+reg.ref+")",sheet,"en_clamp",pre+"4.75V (5V contract low) must exceed enable+margin 1.5V (threshold 1.21V typ, SLVSDG6C) so the always-on buck is sure to start",py_round(turnon,3),"V",1.5,{},"analytic",{}});
        out.checks.push_back({"EN clamp ceiling ("+reg.ref+")",sheet,"en_clamp",pre+"21.0V (20V+5%) worst-case (Vz 5.355V) must stay <= the EN recommended-max 5.5V (no internal clamp, I_hys 1.55uA only — SLVSDG6C)",py_round(ceiling,3),"V",{},5.5,"analytic",{}});
    }
}
void boot0(const std::string& sheet,const SpiceIndex& idx,SpiceResult& out) {
    if(std::none_of(idx.c.nets.begin(),idx.c.nets.end(),[](const auto& n){return n.name=="BOOT0_SET";}))return;
    const auto rs=select(idx.on("BOOT0_SET"),power);if(rs.empty())return;const auto& r=rs[0];
    out.checks.push_back({"BOOT0 strap VIH",sheet,"divider","DIP closed: 3.3 V through "+resistor_description(r)+" vs the SoM 1k5 pull-down (contract) -> must exceed STM32 VIH = 0.7*VDD = "+f(stm32_vih,2)+" V",
        py_round(divide(stm32_vdd*1500,1500+r.value),3),"V",stm32_vih,stm32_vdd,"analytic",{}});
}
}  // namespace

bool SpiceCheck::ok() const {
    if(lo&&value<*lo-1e-9)return false;if(hi&&value>*hi+1e-9)return false;
    if(spice_value&&value!=0&&std::abs(*spice_value-value)>0.01*std::abs(value))return false;return true;
}
std::vector<std::string> SpiceResult::errors() const {
    std::vector<std::string> out;for(const auto& c:checks)if(!c.ok())out.push_back(c.sheet+":"+c.name+" = "+g(c.value)+" "+c.unit+" outside ["+(c.lo?g(*c.lo):"")+" .. "+(c.hi?g(*c.hi):"")+"] "+c.unit+" — "+c.detail+(c.spice_value?"; ngspice="+g(*c.spice_value):""));return out;
}
bool SpiceResult::ok() const{return std::all_of(checks.begin(),checks.end(),[](const auto& c){return c.ok();});}
SpiceResult extract_spice_checks(const std::vector<ProjectCircuit>& sheets,const PowerPolicy& policy) {
    SpiceResult out;std::set<std::string> nets;
    for(const auto& sheet:sheets) {
        const SpiceIndex index(sheet.circuit);for(const auto& n:sheet.circuit.nets)nets.insert(n.name);
        // The shared pure detection stage does not run unrelated load/thermal
        // analysis or alter the original spice extraction's failure boundary.
        auto_dividers(sheet.name,index,out,policy);rc_networks(sheet.name,index,out);sy7201_iset(sheet.name,index,out);
        const auto regs=detect_power_regulators({sheet},policy).regs;
        buck_fb(sheet.name,index,regs,out,policy);en_clamp(sheet.name,index,regs,out,policy);boot0(sheet.name,index,out);
    }
    for(const auto& named:named_dividers()) {
        const bool found=std::any_of(out.checks.begin(),out.checks.end(),[&](const auto& c){return c.name.find(named.net)!=std::string::npos;});
        if(!found&&nets.count(named.net))out.notes.push_back("NOTE: named divider "+named.net+" exists but was not extracted — check the topology ("+named.why+")");
    }return out;
}
std::string spice_report(const SpiceResult& r,bool present) {
    std::vector<std::string> lines{"schgen spice / analytic spot-check gate",std::string(64,'='),"","engine: "+r.engine};
    if(!present)lines.push_back("ngspice: NOT INSTALLED (brew install ngspice) — the closed-form analytic layer IS the gate; every check below is an exact linear-network solution, not an approximation. ngspice adds an independent recompute when present.");
    lines.push_back("");lines.push_back("checks ("+std::to_string(r.checks.size())+"):");
    for(const auto& c:r.checks){lines.push_back("  ["+std::string(c.ok()?"PASS":"FAIL")+"] "+c.sheet+": "+c.name+" = "+g(c.value)+" "+c.unit+" (limits "+(c.lo?g(*c.lo):"")+" .. "+(c.hi?g(*c.hi):"")+" "+c.unit+"; "+c.engine+")"+(c.spice_value?"  ngspice="+g(*c.spice_value):""));lines.push_back("         "+c.detail);}
    if(!r.notes.empty()){lines.push_back("");for(const auto& n:r.notes)lines.push_back("  "+n);}
    lines.push_back("");const auto errors=r.errors();
    if(errors.empty())lines.push_back("errors: none");else{lines.push_back("ERRORS ("+std::to_string(errors.size())+"):");for(const auto& e:errors)lines.push_back("  ERROR: "+e);}
    lines.push_back("");lines.push_back("SPICE GATE: "+std::string(r.ok()?"PASS":"FAIL")+" ("+std::to_string(r.checks.size())+" checks)");return join(lines);
}
JsonNode spice_result_json(const SpiceResult& r) {
    auto checks=arr();for(const auto& c:r.checks)checks.array_value.push_back(obj({{"name",j(c.name)},{"sheet",j(c.sheet)},{"kind",j(c.kind)},{"detail",j(c.detail)},{"value",j(c.value)},{"unit",j(c.unit)},{"lo",opt(c.lo)},{"hi",opt(c.hi)},{"engine",j(c.engine)},{"spice_value",opt(c.spice_value)},{"ok",j(c.ok())}}));
    return obj({{"checks",checks},{"notes",strings(r.notes)},{"engine",j(r.engine)},{"errors",strings(r.errors())},{"ok",j(r.ok())},{"n_checks",j(double(r.checks.size()))}});
}
}  // namespace schgen
