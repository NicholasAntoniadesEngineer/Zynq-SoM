#include "pcb_checks_internal.hpp"
#include "schgen/power_checks.hpp"

namespace schgen {
using namespace pcb_checks;
namespace {
const std::string rating_basis="Hirose DF40 series datasheet: rated current 0.3 A/contact (rated voltage 50 V AC/DC) — CITED (Hirose DF40 catalogue)";
const std::string derating_basis="0.8 (20% power-derating margin on the rated per-contact current) — the standard connector power convention, covering uneven multi-contact load share + temp-rise tolerance — JUDGMENT, fixed floor (LAW 4)";
std::string resolve(const std::string& net,const LinkMapping& m){for(auto p:{&m.rebound_som_rails,&m.vcco_rail_map,&m.function_map,&m.pudc_straps}){auto it=p->find(net);if(it!=p->end())return it->second;}return net;}
bool power(const std::string& net){return starts(net,"+")||net=="VBUS"||starts(net,"VDD")||starts(net,"VCC");}
}
double PcbRailAmpacity::util()const{return capacity_a()>0?current_a/capacity_a():std::numeric_limits<double>::infinity();}
RailAmpacityResult analyze_rail_ampacity(const std::vector<ProjectCircuit>& sheets,const SomInterface& iface,const LinkMapping& mapping){
    RailAmpacityResult res;std::map<std::string,std::map<std::string,int>> counts;for(const auto& [ref,c]:iface.connectors)for(const auto& [pad,net]:c.pins){(void)pad;if(mapping.isolated_som_rails.count(net))continue;auto rail=resolve(net,mapping);if(power(rail))++counts[rail][ref];}
    std::map<std::string,double> delivered;for(const auto& sc:sheets)if(starts(sc.name,"som_j")){
        // Sum each sheet's rail entries before adding to the project total,
        // retaining Python's floating-point evaluation order.
        std::vector<std::pair<std::string,double>> per_sheet;
        for(const auto& load:sc.circuit.loads){auto it=std::find_if(per_sheet.begin(),per_sheet.end(),[&](const auto& v){return v.first==load.rail;});if(it==per_sheet.end())per_sheet.emplace_back(load.rail,load.amps);else it->second+=load.amps;}
        for(const auto& [rail,amps]:per_sheet)delivered[rail]+=amps;
    }
    for(const auto& [name,conns]:counts){int n=0;for(const auto& [ref,count]:conns){(void)ref;n+=count;}PcbRailAmpacity r{name,n,py_round(delivered[name],4),rail_volts(name),conns};res.rails.push_back(r);
        if(r.over())res.errors.push_back("UNDER-CONTACTED: "+name+" carries "+f(r.current_a,3)+" A across "+std::to_string(n)+" DF40 contact(s) but the deratied capacity is only "+f(r.capacity_a(),3)+" A ("+std::to_string(n)+" x 0.3 A x 0.8 derate) — margin "+sign(r.margin_a(),3)+" A; add contacts or reduce the rail current ["+rating_basis+"]");
        if(r.current_a==0)res.findings.push_back(name+": "+std::to_string(n)+" DF40 contact(s) assigned but no SoM-side draw declared on the som_j* sheets — capacity proven, load unbooked (no ampacity risk until a draw is declared)");
    }
    std::sort(res.rails.begin(),res.rails.end(),[](const auto& a,const auto& b){return a.util()==b.util()?a.name<b.name:a.util()>b.util();});return res;
}
std::string RailAmpacityResult::report()const{
    std::vector<std::string> l={"schgen rail-ampacity gate (DF40 power-delivery contact adequacy)",std::string(78,'='),"","model: FAIL when rail_current > n_contacts x "+g(per_contact_a)+" A x "+g(derating)+" derate","  per-contact ampacity : "+rating_basis,"  derating             : "+derating_basis,""};
    auto hdr="  "+pad("rail",14)+" "+pad("V",5,true)+" "+pad("contacts",9,true)+" "+pad("current/A",10,true)+" "+pad("cap/A",8,true)+" "+pad("util",6,true)+" "+pad("margin/A",9,true)+"  verdict";l.push_back(hdr);l.push_back("  "+std::string(hdr.size()-2,'-'));
    for(const auto& r:rails){std::vector<std::string> cs;for(const auto& [ref,n]:r.conns)cs.push_back(ref+":"+std::to_string(n));l.push_back("  "+pad(r.name,14)+" "+pad(r.volts?f(*r.volts,2):"?",5,true)+" "+pad(std::to_string(r.contacts),9,true)+" "+pad(f(r.current_a,3),10,true)+" "+pad(f(r.capacity_a(),3),8,true)+" "+pad(f(r.util(),2),6,true)+" "+pad(sign(r.margin_a(),3),9,true)+"  "+(r.over()?"OVER":"ok")+"  ["+join(cs,"+")+"]");}
    l.push_back("");if(!findings.empty()){l.push_back("findings ("+std::to_string(findings.size())+"):");for(const auto& s:findings)l.push_back("  + "+s);l.push_back("");}
    if(errors.empty())l.push_back("errors: none");else{l.push_back("ERRORS ("+std::to_string(errors.size())+"):");for(const auto& s:errors)l.push_back("  ERROR: "+s);}l.push_back("");l.push_back("RAIL AMPACITY: "+verdict(ok())+" ("+std::to_string(rails.size())+" delivery rails, "+std::to_string(errors.size())+" under-contacted, "+std::to_string(findings.size())+" unbooked)");return join(l);
}
} // namespace schgen
