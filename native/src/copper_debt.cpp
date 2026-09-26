#include "schgen/copper_debt.hpp"
#include "model_checks_internal.hpp"
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <sstream>

namespace schgen {
namespace {
using namespace model_checks;
bool starts(const std::string& s,const std::string& p) { return s.rfind(p,0)==0; }
void claim(bool valid,const std::string& id,const std::string& why) {
    if(!valid) throw CopperProvenanceError("copper_debt "+id+": "+why);
}
std::string number(double n) { std::ostringstream o; o << std::setprecision(6) << n; return o.str(); }
std::string yes(bool b) { return b ? "YES" : "NO"; }
std::string status(bool all,bool partial) { return all ? "EMITTED" : (partial ? "PARTIAL" : "NOTHING"); }
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
std::vector<CopperDebtEntry> entries() {
    // These locations identify structured claim definitions. Correctness is
    // established by verify_sources below, not by searching source text.
    std::vector<CopperDebtEntry> out;
#define ENTRY(id, title, assumes, risk) out.push_back({id,title,assumes,{"native/src/copper_debt.cpp:" + std::to_string(__LINE__)}, "UNMEASURED — no emitted board scanned","UNMEASURED",risk})
    ENTRY("CD-01", "LM61460 pour-aware effective RthJA (58.7 -> 35 C/W)", "full-board In1.Cu GND plane + per-buck thermal-via field (>=6 x 0.6/0.3) at PGND1/PGND2 + local F.Cu/B.Cu GND pours (TI SNVSBD5D 7.3 bare 58.7 C/W vs 25 C/W on a 4-layer board; 11.1.1 layout)", "without this copper Tj(power:U1, 2.42 W) backs out to ~192 C at the bare 58.7 C/W against the 140 C guard — a board-dead thermal PASS-on-fiction (the GAP1 CRITICAL). The thermal gate now HARD-verifies this copper per build.");
    ENTRY("CD-02", "TLV75725 DYD EP thermal-pad RthJA (92.5 C/W)", "DYD thermal pad soldered to GND copper + JESD51-5 pad-adjacent thermal vias into the buried plane (the DS DYD RthJA ~92.5 C/W is DEFINED on that stackup; without it the gate falls back to the DBV bare 231 C/W)", "at the no-copper fallback 231 C/W the VADJ LDO (fmc:U1, 320 mW) lands Tj ~124 C over its 115 C guard — the PWR-3 package swap's entire benefit rides on this copper");
    ENTRY("CD-03", "TPS26631 PWP 2s2p RthJA (33.6 C/W)", "HTSSOP-20 PowerPAD EP soldered to copper with thermal vias into a buried plane (TI SLVSE94 RthJA ~33.6 C/W is the JEDEC 2s2p figure — it presumes internal planes)", "low today (Pd ~54 mW -> huge margin even at several times the 2s2p figure), but the basis string was still plane-predicated while no plane existed");
    ENTRY("CD-04", "CHASSIS_GND island + single-point GND bond", "a CHASSIS_GND copper island (connector shells + mounting ring) joined to signal GND at EXACTLY ONE point (bonding pad / 0R / via stitch near power entry)", "fab'd as-is the shields/mounting ring have NO DC reference (ESD return path open) — ERC/DRC cannot see it because the single-point bond is deliberately not netlisted");
    ENTRY("CD-05", "Bob-Smith trunk copper (BS_COMMON island)", "a Bob-Smith common trunk (4 x 75R || 1n/2kV into BS_COMMON) laid in copper on the chassis-side island, spaced for the 2kV surge rating (IEEE 802.3 40.7.1)", "without trunk copper + spacing the 2kV HF termination exists only as parts; surge creepage and return-path behaviour are unproven until the routing wave draws the island");
    ENTRY("CD-06", "Ethernet isolation moat (In1 plane voids)", "NO GND plane under the ethernet magnetics line side / RJ45 media pins (Pulse HX5008 layout guidance; the 2kV isolation moat) — the full-board In1 plane must be VOIDED there", "a continuous plane under the magnetics bridges the isolation barrier capacitively and violates the 2kV creepage intent; the RJ45<->magnetics media CORRIDOR void remains routing-wave debt");
    ENTRY("CD-07", "DP90/DP100 L2 reference plane", "the DP90_USB / DP100_TMDS trace geometry (widths/gaps in the .kicad_dru + net classes) is an OUTER-layer microstrip referenced to a CONTINUOUS L2 GND plane through one 7628 prepreg sheet", "without the L2 plane every impedance number in the dru is unmoored (return path undefined, impedance wrong by design); with the plane emitted the residual risk is fill VOIDS/splits under a future route path (checked at the routing wave)");
    ENTRY("CD-08", "Under-SoM decoupling fanout vias", "the under-SoM bottom-side rail-entry decoupling (som_decoupling) reaches the rails/planes through fanout vias directly beneath the DF40 mezzanine", "until those vias land the 18 bottom caps decouple nothing (no path from B.Cu pads to the rails) — a routing-wave item, but the prose reads as if the path exists");
#undef ENTRY
    return out;
}
void verify_sources(const CopperDebtSources& s) {
    const auto audited = audit_component_basis(s.circuits);
    claim(audited.ok(),"basis",component_basis_report(audited));
    const auto thermal = [&](const std::string& id,const CircuitPartIr& p,const std::string& prefix,
                             double bare,std::optional<double> poured,const std::string& evidence) {
        claim(starts(p.value,prefix),id,"live component identity differs from claim");
        const auto* spec = thermal_spec_for(p.value,p.footprint,s.thermal);
        claim(spec && spec->rth_ja == bare && spec->rth_ja_pour == poured &&
            spec->pour_evidence == evidence && !spec->cite.empty(),id,"live thermal policy differs from claim");
    };
    for(const auto* scope:{"library","carrier","devkit_mini"}) {
        const auto& power = sheet(s,scope,"power");
        for(const auto* ref:{"U1","U2"}) {
            const auto& p = part(power,ref,"CD-01");
            thermal("CD-01",p,"LM61460",58.7,35.0,"LM61460");
            for(const auto* pin:{"3","9","11"})
                claim(net_of(power,ref,pin)=="GND","CD-01","buck ground pad is not on GND");
        }
        const auto& pd = sheet(s,scope,"pd_input");
        thermal("CD-03",part(pd,"U1","CD-03"),"TPS26631",33.6,std::nullopt,"");
    }
    const auto& fmc = sheet(s,"carrier","fmc");
    thermal("CD-02",part(fmc,"U1","CD-02"),"TLV75725",231.0,92.5,"TLV75725_DYD");
    claim(net_of(fmc,"U1","6")=="GND","CD-02","DYD thermal pad is not on GND");
    const auto need = [&](const std::string& id,const std::string& key,const std::string& prefix,
                          int count,double radius,const std::vector<std::string>& layers) {
        const auto n = std::find_if(s.thermal.pour_needs.begin(),s.thermal.pour_needs.end(),
            [&](const auto& x){return x.first==key;});
        claim(n!=s.thermal.pour_needs.end() && n->second.value_prefix==prefix &&
            n->second.min_vias==count && n->second.radius_mm==radius && n->second.pour_layers==layers,
            id,"thermal evidence requirement differs from claim");
        const auto e = std::find_if(s.emission.thermal_credit_needs.begin(),s.emission.thermal_credit_needs.end(),
            [&](const auto& x){return x.value_prefix==prefix;});
        claim(e!=s.emission.thermal_credit_needs.end() && e->min_vias==count &&
            e->radius_mm==radius && e->pour_layers==layers,id,"emitter and thermal evidence policies disagree");
        const auto c = std::find_if(s.emission.thermal_copper.begin(),s.emission.thermal_copper.end(),
            [&](const auto& x){return x.first==prefix;});
        claim(c!=s.emission.thermal_copper.end() && c->second.max_vias>=static_cast<std::size_t>(count) &&
            c->second.pour_layers==layers && !c->second.cite.empty(),id,"thermal copper emission intent missing");
    };
    need("CD-01","LM61460","LM61460",6,5.2,{"F.Cu","B.Cu"});
    need("CD-02","TLV75725_DYD","TLV75725",2,3.0,{"F.Cu"});
    claim(s.emission.thermal_via_size==0.6 && s.emission.thermal_via_drill==0.3,
        "CD-01","thermal via geometry differs from claim");
    for(const auto* scope:{"carrier","devkit_mini"}) {
        const auto& mechanical = sheet(s,scope,"mechanical");
        claim(mechanical.parts.size()==4,"CD-04","mounting-ring membership changed");
        for(int i=1;i<=4;++i) {
            const auto ref = "H"+std::to_string(i);
            const auto& p = part(mechanical,ref,"CD-04");
            claim(p.lib_id=="Mechanical:MountingHole_Pad" && net_of(mechanical,ref,"1")=="CHASSIS_GND",
                "CD-04","mounting-ring component or chassis connectivity changed");
        }
        const auto& caps = sheet(s,scope,"som_decoupling");
        claim(caps.parts.size()==18,"CD-08","under-SoM cap membership changed");
        for(const auto& p:caps.parts) {
            const auto rail=net_of(caps,p.ref,"1");
            claim(p.lib_id=="Device:C" && !rail.empty() && rail[0]=='+' &&
                net_of(caps,p.ref,"2")=="GND","CD-08","under-SoM cap rail/ground connection changed");
        }
    }
    for(const auto* scope:{"library","carrier"}) {
        const auto& eth = sheet(s,scope,"ethernet");
        const auto& transformer = part(eth,"T1","CD-05");
        claim(starts(transformer.value,"HX5008"),"CD-05","magnetics identity changed");
        for(int i=1;i<=4;++i) {
            const auto r="R"+std::to_string(i), c="C"+std::to_string(i), m="MCT"+std::to_string(i);
            claim(net_of(eth,r,"1")==m && net_of(eth,c,"1")==m &&
                net_of(eth,"T1",std::to_string(27-3*i))==m &&
                net_of(eth,r,"2")=="BS_COMMON" && net_of(eth,c,"2")=="BS_COMMON",
                "CD-05","Bob-Smith branch connectivity changed");
        }
        for(int i=1;i<=5;++i) {
            const auto& c=part(eth,"C"+std::to_string(i),"CD-05");
            const auto lcsc=std::find_if(c.fields.begin(),c.fields.end(),[](const auto& f){return f.key=="LCSC";});
            claim(c.footprint=="Capacitor_SMD:C_1206_3225Metric" && lcsc!=c.fields.end() && lcsc->value=="C9196",
                "CD-05","2kV capacitor selection changed");
        }
        claim(net_of(eth,"C5","1")=="BS_COMMON" && net_of(eth,"C5","2")=="CHASSIS_GND",
            "CD-05","Bob-Smith chassis return changed");
        const auto& jack=part(sheet(s,scope,"rj45_connector"),"J1","CD-06");
        for(const auto* p:{&transformer,&jack}) claim(
            std::any_of(s.emission.isolation_prefixes.begin(),s.emission.isolation_prefixes.end(),
                [&](const auto& prefix){return !prefix.empty() && starts(p->value,prefix);}),
            "CD-06","live magnetics/jack omitted by isolation policy");
    }
    claim(s.emission.ground_layer=="In1.Cu" && s.emission.isolation_margin>0,
        "CD-06","isolation/reference-layer policy differs from claim");
    for(const auto impedance:{90,100}) {
        const auto g=std::find_if(s.geometry.begin(),s.geometry.end(),[&](const auto& x){return x.impedance==impedance;});
        claim(g!=s.geometry.end() && g->width_mm==(impedance==90 ? 0.2611 : 0.2052) &&
            g->gap_mm==0.2032 && g->source=="JLCPCB calculator, JLC04161H-7628 outer/L2",
            "CD-07","live researched impedance geometry differs from claim");
    }
}
} // namespace
CopperDebtSources author_copper_debt_sources(const std::filesystem::path& repository) {
    CopperDebtSources s;
    s.circuits=author_component_basis_inputs(repository);
    s.thermal=default_thermal_policy(); s.emission=default_pcb_emit_policy();
    for(const int impedance:{90,100}) {
        const auto* g=differential_geometry(impedance);
        if(!g) throw CopperProvenanceError("missing native differential geometry");
        s.geometry.push_back(*g);
    }
    return s;
}
CopperDebtResult analyze_copper_debt(const ThermalCopper* c,const CopperDebtSources& s) {
    verify_sources(s);
    CopperDebtResult result{entries(),"NO BOARD SCANNED (statuses UNMEASURED)"};
    if(!c) return result;
    std::size_t fills=0,rules=0,gnd=0;
    for(const auto& z:c->zones) { if(!z.keepout && z.filled) ++fills; if(z.keepout) ++rules; }
    for(const auto& v:c->vias) if(v.net_name=="GND") ++gnd;
    const bool plane=c->gnd_plane();
    result.inventory=std::to_string(fills)+" fill zones ("+(plane?"with":"NO")+
        " In1.Cu GND plane), "+std::to_string(rules)+" rule areas, "+std::to_string(c->vias.size())+
        " vias ("+std::to_string(gnd)+" GND), "+std::to_string(c->segments)+" segments";
    for(int i=0;i<3;++i) {
        auto& e=result.entries[static_cast<std::size_t>(i)];
        const auto instances=c->instances(i==0?"LM61460":i==1?"TLV75725":"TPS26631");
        bool all=!instances.empty() && plane, partial=plane;
        std::string rows;
        for(const auto* f:instances) {
            if(!rows.empty()) rows+="; ";
            if(i==2) {
                std::size_t n=0;
                for(const auto& p:f->pads) if(p.drill>0 && p.net_name=="GND" && std::hypot(p.dx,p.dy)<=1.5) ++n;
                all=all && n>=4; partial=true;
                rows+=f->ref+": "+std::to_string(n)+" in-footprint EP via-pads (GND, PTH)";
            } else {
                const auto n=c->gnd_vias_within(f->x,f->y,i==0?5.2:3.0);
                const bool front=c->pour_at(f->x,f->y,"F.Cu"), back=c->pour_at(f->x,f->y,"B.Cu");
                all=all && n>=static_cast<std::size_t>(i==0?6:2) && front && (i!=0 || back);
                partial=partial || n!=0;
                rows+=f->ref+": "+std::to_string(n)+" GND vias<="+(i==0?"5.2":"3.0")+"mm, F.Cu pour "+yes(front);
                if(i==0) rows+=", B.Cu pour "+yes(back);
            }
        }
        e.emits="In1.Cu GND plane: "+yes(plane)+"; "+rows; e.status=status(all,partial);
    }
    for(std::size_t i=3;i<=4;++i) {
        auto& e=result.entries[i];
        const std::string net=i==3?"CHASSIS_GND":"BS_COMMON";
        const auto [z,v]=net_copper(*c,net);
        e.emits=net+" board-level copper: "+std::to_string(z)+" zones, "+std::to_string(v)+" vias "+
            (i==3?"(pads only otherwise); no bond stitch emitted":"(pads only)");
        e.status=status(z!=0 && v!=0,z!=0 || v!=0);
    }
    const auto voids=zones(*c,"ethernet_isolation_void");
    std::string names;
    for(const auto* z:voids) { if(!names.empty()) names+=", "; names+=z->name; }
    result.entries[5].emits="In1 rule-area voids: "+(names.empty()?"none":names)+"; corridor between them: NOT voided (debt)";
    result.entries[5].status=(!plane ? !voids.empty() : voids.size()>=2) ? "PARTIAL" : "NOTHING";
    auto& dp=result.entries[6]; dp.status="NOTHING"; dp.emits="no GND fill zone on In1.Cu";
    for(const auto& z:c->zones) if(!z.keepout && z.filled && z.net_name=="GND" &&
        std::find(z.layers.begin(),z.layers.end(),"In1.Cu")!=z.layers.end()) {
        dp.status="EMITTED";
        dp.emits="In1.Cu GND plane zone "+number(z.bbox[0])+","+number(z.bbox[1])+" -> "+
            number(z.bbox[2])+","+number(z.bbox[3])+" mm (unfilled-on-disk, DRC-refilled); ethernet voids punch it locally (CD-06)";
        break;
    }
    const auto som=zones(*c,"SoM_body_keepout"); std::size_t n=0;
    if(!som.empty()) for(const auto& v:c->vias) if(v.net_name=="GND" &&
        som[0]->bbox[0]<=v.x && v.x<=som[0]->bbox[2] && som[0]->bbox[1]<=v.y && v.y<=som[0]->bbox[3]) ++n;
    result.entries[7].emits="GND vias inside the SoM body zone: "+std::to_string(n)+" (SoM zone "+
        (som.empty()?"NOT found":"found")+"); rail fanout vias: none emitted";
    result.entries[7].status=n?"PARTIAL":"NOTHING";
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
