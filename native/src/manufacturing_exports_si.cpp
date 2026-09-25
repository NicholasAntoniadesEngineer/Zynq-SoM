#include "schgen/manufacturing_exports.hpp"
#include "manufacturing_exports_internal.hpp"

namespace schgen {
using namespace manufacturing_detail;
namespace {
const std::string banner="# ==== SI CONSTRAINTS (schgen/generate/si_constraints.py) ====";
SiPairKey key(const PairSignalSpec& p){return {p.net_p,p.net_n};}
std::string names(const SiPairKey& k,const std::string& sep){return join({k.begin(),k.end()},sep);}
}
std::string si_group_id(const std::string& s){auto tok=safe(s);for(auto& c:tok)if(c>='a'&&c<='z')c-=32;return "LM_"+tok;}
SiConstraintsModel build_si_constraints(const std::vector<ProjectCircuit>& sheets,const std::vector<PairSignalSpec>& spec){
    SiConstraintsModel m;
    for(const auto& sc:sheets)for(const auto& net:sc.circuit.nets)if(net.net_class=="port"){
        const auto p=circuit_port_type(sc.circuit,net.name);
        if((p.kind=="diff_pair"||p.kind=="usb_hs_pair"||p.kind=="tmds_pair")&&!p.pair_with.empty())
            m.declared.emplace(SiPairKey{net.name,p.pair_with},SiDeclaration{sc.name,p.kind,p.has_impedance?p.impedance:0});
    }
    std::set<SiPairKey> spec_keys;
    for(const auto& p:spec){spec_keys.insert(key(p));(m.declared.count(key(p))?m.pairs:m.missing_in_schematic).push_back(p);}
    for(const auto& [k,d]:m.declared){(void)d;if(!spec_keys.count(k))m.missing_in_spec.push_back(k);}
    std::stable_sort(m.pairs.begin(),m.pairs.end(),[](const auto& a,const auto& b){return std::tie(a.interface,a.net_p)<std::tie(b.interface,b.net_p);});
    std::map<std::string,std::vector<PairSignalSpec>> groups;
    for(const auto& p:m.pairs)groups[p.interface].push_back(p);
    for(auto& [iface,ps]:groups){double tol=ps.front().match_tol_mil;for(const auto& p:ps)tol=std::min(tol,p.match_tol_mil);m.groups.push_back({si_group_id(iface),iface,std::move(ps),tol});}
    return m;
}
SiConstraintsModel load_si_constraints(const std::vector<ProjectCircuit>& sheets,const std::filesystem::path& path){
    if(!std::filesystem::exists(path)){
        auto empty=build_si_constraints(sheets,{});
        if(empty.declared.empty())return empty;
        throw ProjectError(path.string()+" not found — the vendored SI target table is required (committed under the project's research/).");
    }return build_si_constraints(sheets,load_signal_specs(path));
}
SiConstraintsVerdict check_si_constraints(const SiConstraintsModel& m){
    SiConstraintsVerdict v;v.n_pairs=m.pairs.size();v.n_groups=m.groups.size();std::set<SiPairKey> emitted;
    for(const auto& p:m.pairs){auto k=key(p);emitted.insert(k);int d=m.declared.at(k).impedance;if(d!=p.z_diff_ohm)v.z_divergent.emplace_back(*k.begin(),d,p.z_diff_ohm);}
    for(const auto& [k,d]:m.declared){(void)d;if(!emitted.count(k))v.uncovered.push_back(k);}
    std::sort(v.z_divergent.begin(),v.z_divergent.end());v.ok=v.uncovered.empty()&&v.z_divergent.empty();return v;
}
std::string SiConstraintsVerdict::summary()const{
    const auto head="SI constraints: "+std::to_string(n_pairs)+" diff pairs, "+std::to_string(n_groups)+" length-match groups emitted";
    if(ok)return head+" — every declared pair covered.";
    std::vector<std::string> parts;
    if(!uncovered.empty()){std::vector<std::string> a;for(const auto& k:uncovered)a.push_back(names(k,"/"));parts.push_back("UNCOVERED declared pair(s): "+join(a,"; "));}
    if(!z_divergent.empty()){std::vector<std::string> a;for(const auto& [n,d,r]:z_divergent)a.push_back(n+" "+std::to_string(d)+"R vs "+std::to_string(r)+"R");parts.push_back("DECLARED impedance != researched z_diff_ohm: "+join(a,"; "));}
    return head+" — "+join(parts," | ");
}
std::string render_si_design_rules(const SiConstraintsModel& m,std::string base){
    if(auto p=base.find(banner);p!=base.npos)base.resize(p);
    while(!base.empty()&&base.back()=='\n')base.pop_back();
    std::ostringstream o;o<<base<<"\n\n"<<banner<<R"(
# Differential-pair + matched-length rules harvested from the schematic's
# typed ports and joined to carrier/research/si_spec.json (researched
# targets, standard-cited). Intra-pair skew = P/N length match within a
# pair; group length = inter-pair match across a port/bus. Enforced by
# KiCad DRC once the pairs are routed. NOT routing — constraints only.

)";
    for(const auto& p:m.pairs)o<<"(rule \"intra_skew_"<<safe(p.net_p)<<"\"\n  # "<<p.interface<<" — "<<p.signal<<"; Zdiff "<<p.z_diff_ohm<<"ohm; "<<(p.ac_coupled?"AC-coupled":"DC-coupled")<<"\n  # spec: "<<p.spec_cite<<"\n  (condition \"(A.NetName == '"<<p.net_p<<"' && B.NetName == '"<<p.net_n<<"') || (A.NetName == '"<<p.net_n<<"' && B.NetName == '"<<p.net_p<<"')\")\n  (constraint skew (max "<<pyfloat(decimal_round(p.intra_pair_skew_mil*0.0254,4))<<"mm))\n)\n\n";
    for(const auto& g:m.groups){std::vector<std::string> cond;for(const auto& p:g.members){cond.push_back("A.NetName == '"+p.net_p+"'");cond.push_back("A.NetName == '"+p.net_n+"'");}
        o<<"(rule \"lenmatch_"<<g.gid<<"\"\n  # "<<g.interface<<": "<<g.members.size()<<" pair(s) length-matched as a group (inter-pair), tol +/-"<<general(g.tol_mil)<<" mil\n  (condition \""<<join(cond," || ")<<"\")\n  (constraint skew (max "<<pyfloat(decimal_round(g.tol_mil*0.0254,4))<<"mm))\n)\n\n";}
    return o.str();
}
std::string render_si_markdown(const SiConstraintsModel& m){
    std::ostringstream o;o<<R"(# Signal-Integrity Constraints — Zynq Carrier

GENERATED by `schgen/generate/si_constraints.py` (do not hand-edit).
Source of targets: `carrier/research/si_spec.json` (researched, standard-cited); pairs are harvested from the schematic's typed ports (`c.port_type(kind=..., pair_with=..., impedance=...)`) so this table only lists pairs that actually exist on the board.

**)"<<m.pairs.size()<<" differential pairs** in **"<<m.groups.size()<<R"( length-match groups**. These are CONSTRAINTS for the layout engineer / KiCad DRC — no routing is implied. The matching rules are also emitted into `Zynq_Carrier_pcb.kicad_dru` (KiCad design rules).

## Stackup

JLCPCB JLC04161H-7628, 4-layer 1.6 mm (Sig / GND / PWR / Sig). Diff-pair trace geometry (width/gap) per class lives in the `.kicad_pro` net_settings + `.kicad_dru`: 90R = 0.2611/0.2032 mm, 100R = 0.2052/0.2032 mm (JLCPCB impedance calculator, this stackup).

## Differential pairs

| Interface | Signal | net_p | net_n | Z_diff (ohm) | Intra-pair skew | Length-match group | Group tol | AC-coupled | Net class | Spec |
|---|---|---|---|---|---|---|---|---|---|---|
)";
    std::map<SiPairKey,const SiLengthGroup*> group;
    for(const auto& g:m.groups)for(const auto& p:g.members)group[key(p)]=&g;
    for(const auto& p:m.pairs){
        const auto& g=*group.at(key(p));const auto& d=m.declared.at(key(p));CircuitPortIr port;port.kind=d.kind;port.has_impedance=true;port.impedance=d.impedance?d.impedance:p.z_diff_ohm;
        o<<"| "<<p.interface<<" | "<<p.signal<<" | `"<<p.net_p<<"` | `"<<p.net_n<<"` | "<<p.z_diff_ohm<<" | +/-"<<general(p.intra_pair_skew_mil)<<" mil ("<<pyfloat(decimal_round(p.intra_pair_skew_mil*0.0254,4))<<" mm) | "<<g.gid<<" | +/-"<<general(g.tol_mil)<<" mil ("<<pyfloat(decimal_round(g.tol_mil*0.0254,4))<<" mm) | "<<(p.ac_coupled?"yes":"no")<<" | "<<port_net_class(port)<<" | "<<p.spec_cite<<" |\n";
    }
    o<<R"(
## Length-match groups

Each group's pairs must be length-matched **to each other** (inter-pair) to the group tolerance; within every pair, P and N match to the intra-pair skew above.

| Group | Interface | Pairs | Group match tol | Members |
|---|---|---|---|---|
)";
    for(const auto& g:m.groups){std::vector<std::string> mem;for(const auto& p:g.members)mem.push_back("`"+p.net_p+"`/`"+p.net_n+"`");
        o<<"| "<<g.gid<<" | "<<g.interface<<" | "<<g.members.size()<<" | +/-"<<general(g.tol_mil)<<" mil ("<<pyfloat(decimal_round(g.tol_mil*0.0254,4))<<" mm) | "<<join(mem,", ")<<" |\n";}
    if(!m.missing_in_spec.empty()||!m.missing_in_schematic.empty()){
        o<<"\n## Notes / coverage gaps\n\n";
        for(const auto& k:m.missing_in_spec)o<<"- DECLARED in schematic but NO si_spec row: `"<<names(k,"`/`")<<"` (no SI target emitted)\n";
        for(const auto& p:m.missing_in_schematic)o<<"- si_spec row not present in schematic: "<<p.interface<<" `"<<p.net_p<<"`/`"<<p.net_n<<"` ("<<first_chars(p.notes,80)<<")\n";
    }return o.str();
}
} // namespace schgen
