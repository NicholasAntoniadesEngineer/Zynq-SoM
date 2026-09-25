#include "schgen/bringup_facts.hpp"
#include "bringup_internal.hpp"
#include "bringup_unicode.hpp"
#include "verification_internal.hpp"
#include "verification_unicode.hpp"
#include <regex>

namespace schgen {
using namespace bringup_detail;

std::optional<double> bringup_parse_value_ohms(const std::string& value) {
    std::string normalized;
    for(const auto& [cp,bytes]:verification::utf8(value)) {
        const int digit=decimal_digit(cp);
        if(digit>=0)normalized+=static_cast<char>('0'+digit);
        else if(verification::space(cp))normalized+=' ';
        else normalized+=bytes;
    }
    const auto v=verification::strip(normalized);std::smatch m;
    static const std::regex plain(R"((\d+(?:\.\d+)?)\s*(m|k|M)?(?:R|ohm)?)"), embedded(R"((\d+)(k|M)(\d+))");
    if(std::regex_match(v,m,plain))return std::stod(m[1])*(m[2]=="m"?.001:m[2]=="k"?1000:m[2]=="M"?1e6:1);
    if(std::regex_match(v,m,embedded))return std::stod(m[1].str()+"."+m[3].str())*(m[2]=="k"?1000:1e6);
    return std::nullopt;
}
std::string bringup_c_ident(const std::string& net) {
    std::string out;
    const auto codepoints=verification::utf8(net);
    for(const auto& [cp,bytes]:codepoints)out+=cp=='+'?"P":verification::unicode_word(cp)?bytes:"_";
    if(!codepoints.empty()&&unicode_digit(codepoints.front().first))out="_"+out;
    return out;
}
Stm32PinMap stm32_pin_map(const SomZynq& live,const SomInterface& contract) {
    std::map<std::string,std::vector<std::string>> jpins;
    for(const auto& [conn,data]:contract.connectors) for(const auto& [pin,net]:data.pins)jpins[net].push_back(conn+"."+pin);
    for(auto& entry:jpins)std::stable_sort(entry.second.begin(),entry.second.end(),[](const auto& a,const auto& b){
        const auto ap=a.find('.'),bp=b.find('.');
        return std::make_pair(a.substr(0,ap),std::stoi(a.substr(ap+1)))<std::make_pair(b.substr(0,bp),std::stoi(b.substr(bp+1)));
    });
    Stm32PinMap out;out.value=live.value.value_or("None");
    static const std::regex gpio(R"(P([A-G])(\d+))");
    for(const auto& [num,net]:live.ball_net) {
        if(starts(net,"unconnected-"))continue;
        std::smatch m;const auto pname=lookup(live.pin_names,num);
        if(!std::regex_match(pname,m,gpio))continue;
        Stm32Net e{net,m[1],std::stoi(m[2]),jpins[net]};
        (e.j_pins.empty()?out.internal:out.nets)[net]=std::move(e);
    }return out;
}
std::vector<std::string> dip_switch_refs(const CircuitSheetIr& c) {return Index(c).matching("DSHP");}
std::vector<DipPosition> dip_positions(const CircuitSheetIr& c,const std::string& ref,const std::vector<std::string>& common) {
    Index ix(c);const int total=static_cast<int>(ix.part(ref).pin_numbers.size());
    std::map<int,std::vector<const CircuitNetIr*>> candidates;
    for(const auto* n:ix.nets(ref)) for(const auto& p:n->pins) if(p.ref==ref) {
        const int pin=std::stoi(p.pin);candidates[std::min(pin,total+1-pin)].push_back(n);
    }
    std::vector<DipPosition> out;
    for(auto& [pos,nets]:candidates) {
        nets.erase(std::remove_if(nets.begin(),nets.end(),[&](const auto* n){return contains(common,n->name);}),nets.end());
        if(nets.empty())continue;
        std::stable_sort(nets.begin(),nets.end(),[](const auto* a,const auto* b){return std::make_pair(a->net_class!="port",a->name)<std::make_pair(b->net_class!="port",b->name);});
        out.push_back({ref,pos,nets.front()->name});
    }return out;
}
std::vector<EnCell> en_cells(const CircuitSheetIr& c) {
    Index ix(c);std::vector<EnCell> out;
    for(const auto& ref:ix.matching("74LVC1G08"))out.push_back({c.name,ref,ix.at(ref,"1").value_or("?"),ix.at(ref,"2").value_or("?"),ix.at(ref,"4").value_or("?")});
    return out;
}
BringupExpander bringup_expander(const CircuitSheetIr& c) {
    Index ix(c);const auto refs=ix.matching("TCA9535");
    if(refs.size()!=1)throw FirmwareDocsError(c.name+": expected exactly one TCA9535, found "+repr(refs));
    const auto ref=refs.front();const auto vcc=ix.named(ref,"VCC");int addr=0x20;
    for(int bit=0;bit<3;++bit) {
        const auto strap="A"+std::to_string(bit);const auto net=ix.named(ref,strap);
        if(net==vcc)addr|=1<<bit;
        else if(net!=std::optional<std::string>("GND"))throw FirmwareDocsError(c.name+": TCA9535 "+strap+" on "+repr(net)+" — not a valid GND/VCC strap");
    }
    BringupExpander out{ref,addr,{}};static const std::regex port("P[01][0-7]");
    for(const auto& p:ix.part(ref).pin_names)if(std::regex_match(p.name,port))out.ports.emplace_back(p.name,ix.at(ref,p.numbers.at(0)).value_or("?"));
    return out;
}
std::vector<BringupMonitor> ina3221_monitors(const CircuitSheetIr& c) {
    Index ix(c);std::vector<BringupMonitor> out;
    for(const auto& ref:ix.matching("INA3221")) {
        const auto a0=ix.named(ref,"A0");
        const std::vector<std::optional<std::string>> straps{std::string("GND"),ix.named(ref,"VS"),ix.named(ref,"SDA"),ix.named(ref,"SCL")};
        int strap=-1;for(int i=0;i<4;++i)if(straps[i]==a0)strap=i; // Python dict: last duplicate key wins.
        if(strap<0)throw FirmwareDocsError(c.name+": "+ref+" A0 on "+repr(a0)+" — unknown strap");
        BringupMonitor m{ref,0x40+strap,{}};
        for(int ch=1;ch<=3;++ch)m.channels[ch]={ix.named(ref,"IN+"+std::to_string(ch)).value_or("?"),ix.named(ref,"IN-"+std::to_string(ch)).value_or("?")};
        out.push_back(std::move(m));
    }std::stable_sort(out.begin(),out.end(),[](const auto& a,const auto& b){return a.addr<b.addr;});return out;
}
namespace {
std::set<std::string> rails_of(const Index& ix,const std::string& ref) {
    std::set<std::string> out;for(const auto* n:ix.nets(ref))if(n->net_class=="power"&&n->name!="+3V3_SC")out.insert(n->name);return out;
}
std::pair<std::string,std::string> canonical_rail(const std::string& a,const std::string& b) {
    for(const std::string suf:{"_REG","_SYS"}) {
        if(ends(a,suf)&&a.substr(0,a.size()-suf.size())==b)return {b,a};
        if(ends(b,suf)&&b.substr(0,b.size()-suf.size())==a)return {a,b};
    }return a.size()<=b.size()?std::make_pair(a,b):std::make_pair(b,a);
}
std::optional<double> stage_vout(const Index& ix,const std::string& ref,const std::string& value) {
    std::smatch m;static const std::regex suffix(R"(-(\d+(?:\.\d+)?)$)");
    if(std::regex_search(value,m,suffix))return std::stod(m[1]);
    auto vref=fb_vref(value);if(!vref)return std::nullopt;
    for(const auto* net:ix.nets(ref)) {
        if(net->net_class!="signal")continue;
        std::vector<std::string> rs;for(const auto& p:net->pins)if(starts(p.ref,"R"))rs.push_back(p.ref);
        if(rs.size()<2)continue;
        std::optional<double> top,bot;
        for(const auto& r:rs) {
            bool gnd=false,power=false;
            for(const auto* n:ix.nets(r))if(n->name!=net->name){gnd|=n->name=="GND";power|=n->net_class=="power";}
            if(gnd)bot=bringup_parse_value_ohms(ix.part(r).value);
            else if(power)top=bringup_parse_value_ohms(ix.part(r).value);
        }
        if(top&&bot&&*top!=0&&*bot!=0)return decimal_round(*vref*(1+*top/ *bot),2);
    }return std::nullopt;
}
}
std::vector<RegulatorStage> regulator_chain(const CircuitSheetIr& power,const std::string& root,const CircuitSheetIr* monitor) {
    Index ix(power);ProjectStrings regs;
    for(const auto& n:power.nets)if(n.net_class=="port"&&starts(n.name,"EN_"))for(const auto& p:n.pins) {
        if(ix.part(p.ref).lib_id=="Connector:TestPoint")continue;
        auto found=std::find_if(regs.begin(),regs.end(),[&](const auto& r){return r.first==p.ref;});
        if(found==regs.end())regs.emplace_back(p.ref,n.name);else found->second=n.name;
    }
    std::map<std::string,std::string> alias;
    if(monitor) {
        // Keep pin occurrences (not only distinct nets), as the source does.
        std::map<std::string,std::vector<const CircuitNetIr*>> netted;
        for(const auto& n:monitor->nets)for(const auto& p:n.pins)netted[p.ref].push_back(&n);
        for(const auto& [ref,nets]:netted) {
            (void)ref;
            if(nets.size()!=2||nets[0]->net_class!="power"||nets[1]->net_class!="power"||nets[0]->name==nets[1]->name)continue;
            const auto pair=canonical_rail(nets[0]->name,nets[1]->name);alias[pair.second]=pair.first;
        }
    }
    const auto resolve=[&](std::string r){std::set<std::string> seen;while(alias.count(r)&&seen.insert(r).second)r=alias.at(r);return r;};
    std::map<std::string,std::set<std::string>> pending;
    for(const auto& [ref,en]:regs) {
        (void)en;auto rails=rails_of(ix,ref);
        for(const auto& l:power.parts)if(l.lib_id=="Device:L") {
            bool shared=false;
            for(const auto* n:ix.nets(ref))if(n->net_class=="signal")
                for(const auto& p:n->pins)if(p.ref==l.ref)shared=true;
            if(shared){auto ls=rails_of(ix,l.ref);rails.insert(ls.begin(),ls.end());}
        }
        auto& p=pending[ref];for(const auto& r:rails)p.insert(resolve(r));
    }
    std::set<std::string> known{resolve(root)};std::vector<RegulatorStage> out;
    while(!pending.empty()) {
        auto ready=pending.end();std::string rin,rout;
        for(auto i=pending.begin();i!=pending.end();++i) {
            std::vector<std::string> yes,no;for(const auto& r:i->second)(known.count(r)?yes:no).push_back(r);
            if(yes.size()==1&&no.size()==1){ready=i;rin=yes[0];rout=no[0];break;}
        }
        if(ready==pending.end()) {
            std::vector<std::string> desc;
            for(const auto& [ref,en]:regs)if(pending.count(ref)) { (void)en;const auto& rails=pending.at(ref);desc.push_back(quoted(ref)+": "+repr(std::vector<std::string>(rails.begin(),rails.end()))); }
            throw FirmwareDocsError("power-tree walk stuck: known="+repr(std::vector<std::string>(known.begin(),known.end()))+", pending={"+join(desc,", ")+"}");
        }
        const auto ref=ready->first;const auto& part=ix.part(ref);
        out.push_back({ref,part.value,lookup(regs,ref),rin,rout,stage_vout(ix,ref,part.value),std::nullopt});
        known.insert(rout);pending.erase(ready);
    }
    for(auto& st:out) {
        const auto token=remove_prefix(st.enable,"EN_");
        for(const auto& n:power.nets)if(starts(n.name,"PG_"+token))for(const auto& p:n.pins)if(starts(p.ref,"D"))st.pg_led=p.ref;
        if(!st.pg_led)for(const auto& n:power.nets)if(n.name==st.rail_out)for(const auto& p:n.pins)if(starts(p.ref,"D"))st.pg_led=p.ref;
    }return out;
}
std::vector<ModuleGate> module_gates(const CircuitSheetIr& c) {
    Index ix(c);std::vector<ModuleGate> out;
    for(const auto& ref:ix.matching("SY6280")) {
        auto en=ix.named(ref,"EN").value_or("?");auto rail=ix.named(ref,"OUT").value_or("?");auto iset=ix.named(ref,"ISET");
        std::optional<int> ilim;std::optional<std::string> led;
        for(const auto& n:c.nets) {
            if(iset&&n.name==*iset)for(const auto& p:n.pins)if(starts(p.ref,"R")) {auto ohms=bringup_parse_value_ohms(ix.part(p.ref).value);if(ohms&&*ohms)ilim=static_cast<int>(rounded(6800/ *ohms*1000));}
            if(n.name==rail)for(const auto& p:n.pins)if(starts(p.ref,"D"))led=p.ref;
        }
        out.push_back({ref,remove_prefix(en,"EN_"),ix.named(ref,"IN").value_or("?"),rail,en,ilim,led});
    }std::stable_sort(out.begin(),out.end(),[](const auto& a,const auto& b){return ref_key(a.ref)<ref_key(b.ref);});return out;
}
std::optional<int> bringup_shunt_mohm(const CircuitSheetIr& c,const std::string& inp,const std::string& inn) {
    Index ix(c);std::set<std::string> ps,ns;
    for(const auto& n:c.nets)if(n.name==inp||n.name==inn)for(const auto& p:n.pins)if(starts(p.ref,"RS")) {
        if(n.name==inp)ps.insert(p.ref);if(n.name==inn)ns.insert(p.ref);
    }
    for(const auto& ref:ps)if(ns.count(ref)) {auto v=bringup_parse_value_ohms(ix.part(ref).value);if(v)return static_cast<int>(rounded(*v*1000));}
    return std::nullopt;
}
int bringup_id_eeprom_addr(const CircuitSheetIr& c) {
    Index ix(c);const CircuitPartIr* part=nullptr;
    for(const auto& p:c.parts)if(has(p.lib_id,"24AA025E48")){part=&p;break;}
    if(!part)throw FirmwareDocsError("board_services no longer carries a 24AA025E48 ID-EEPROM — I2C address map stale");
    int addr=0x50;
    for(int bit=0;bit<2;++bit) {
        const auto pin=std::to_string(5-bit);const auto* net=ix.net(part->ref,pin);
        if(!net)throw FirmwareDocsError("ID-EEPROM A"+std::to_string(bit)+" strap (pin "+pin+") floats");
        if(net->net_class=="power")addr|=1<<bit;
    }return addr;
}
} // namespace schgen
