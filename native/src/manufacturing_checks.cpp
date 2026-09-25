#include "schgen/manufacturing_checks.hpp"
#include "manufacturing_exports_internal.hpp"
#include <functional>

namespace schgen {
using namespace manufacturing_detail;
namespace {
const SexprList* list(const Sexpr& n){return std::get_if<SexprList>(&n.v);}
bool tag(const Sexpr& n,const std::string& key){const auto* a=list(n);return a&&!a->empty()&&std::holds_alternative<Sexpr::Sym>((*a)[0].v)&&std::get<Sexpr::Sym>((*a)[0].v).name==key;}
const SexprList* sub(const Sexpr& n,const std::string& key){if(auto a=list(n))for(const auto& v:*a)if(tag(v,key))return list(v);return nullptr;}
double value(const Sexpr& n){if(auto p=std::get_if<double>(&n.v))return *p;if(auto p=std::get_if<bool>(&n.v))return *p?1:0;if(auto p=std::get_if<std::string>(&n.v)){auto s=verification::strip(*p);std::size_t used=0;auto d=std::stod(s,&used);if(used==s.size())return d;}throw ProjectError("non-numeric board dimension");}
std::optional<double> minimum(const std::vector<double>& v){return v.empty()?std::nullopt:std::optional<double>(*std::min_element(v.begin(),v.end()));}
std::optional<double> rule(const std::string& text,const std::string& pattern,bool first=false){std::regex re(pattern);std::vector<double> vals;for(std::sregex_iterator i(text.begin(),text.end(),re),end;i!=end;++i){vals.push_back(std::stod((*i)[1]));if(first)break;}return minimum(vals);}
}
const ManufacturingFabProfile& manufacturing_jlcpcb_4l(){static const ManufacturingFabProfile p{"JLCPCB standard 4-layer (1oz)",0.09,0.09,0.15,0.25,0.075,0.15,"JLCPCB PCB Manufacturing & Assembly Capabilities (jlcpcb.com/capabilities/pcb-capabilities) + JLCPCB via/annular Q&A; retrieved 2026-07"};return p;}
ManufacturingBoardDemand measure_manufacturing_board(const Sexpr& pcb,const std::string& dru,const std::string& project){
    ManufacturingBoardDemand d;std::vector<double> widths,dias,annuli,drills;
    std::function<void(const Sexpr&)> walk=[&](const Sexpr& n){if(auto a=list(n))for(const auto& child:*a){if(!list(child)||list(child)->empty())continue;
        if(tag(child,"segment")){if(auto w=sub(child,"width");w&&w->size()>1)widths.push_back(value((*w)[1]));}
        else if(tag(child,"via")){auto sz=sub(child,"size"),dr=sub(child,"drill");std::optional<double> dia,drill;
            if(sz&&sz->size()>1){dia=value((*sz)[1]);dias.push_back(*dia);}if(dr&&dr->size()>1){drill=value((*dr)[1]);drills.push_back(*drill);}if(dia&&drill)annuli.push_back(decimal_round((*dia-*drill)/2,6));}
        else if(tag(child,"pad")){if(auto dr=sub(child,"drill")){std::vector<double> ns;for(std::size_t i=1;i<dr->size();++i)if(std::holds_alternative<double>((*dr)[i].v)||std::holds_alternative<bool>((*dr)[i].v))ns.push_back(value((*dr)[i]));if(auto v=minimum(ns))drills.push_back(*v);}}
        walk(child);
    }};walk(pcb);
    d.n_segments=widths.size();d.n_vias=dias.size();d.n_drills=drills.size();
    const std::string number=R"(([-+]?\d*\.?\d+))";
    if(auto v=rule(dru,R"(track_width\s*\(min\s*)"+number+"mm"))widths.push_back(*v);
    d.min_trace_mm=minimum(widths);d.min_clearance_mm=rule(dru,R"(\bclearance\s*\(min\s*)"+number+"mm");
    d.min_drill_mm=minimum(drills);d.min_via_dia_mm=minimum(dias);d.min_via_annular_mm=minimum(annuli);
    d.pro_via_annular_mm=rule(project,"\"min_via_annular_width\"\\s*:\\s*"+number,true);
    d.min_hole_to_hole_mm=rule(project,"\"min_hole_to_hole\"\\s*:\\s*"+number,true);return d;
}
ManufacturingBoardDemand measure_manufacturing_board(const std::filesystem::path& pcb,const std::filesystem::path& dru,const std::filesystem::path& project){
    if(!std::filesystem::exists(pcb))return {};
    return measure_manufacturing_board(sexpr_loads(read(pcb)),std::filesystem::exists(dru)?read(dru):"",std::filesystem::exists(project)?read(project):"");
}
ManufacturingFabResult check_manufacturing_fab(const ManufacturingBoardDemand& d,const ManufacturingFabProfile& p){
    ManufacturingFabResult r;r.profile=p;r.demand=d;
    for(const auto& [label,v,floor]:std::vector<std::tuple<std::string,std::optional<double>,double>>{
        {"min trace width",d.min_trace_mm,p.min_trace_mm},{"min clearance",d.min_clearance_mm,p.min_clearance_mm},{"min drill",d.min_drill_mm,p.min_drill_mm},{"min via diameter",d.min_via_dia_mm,p.min_via_dia_mm},{"min via annular",d.min_via_annular_mm,p.min_via_annular_mm},{"min hole-to-hole",d.min_hole_to_hole_mm,p.min_hole_to_hole_mm}}){
        bool ok=!v||*v>=floor-1e-6;r.rows.emplace_back(label,v,floor,ok);if(!ok){r.ok=false;r.errors.push_back(label+": board demands "+fixed(*v,4)+" mm but "+p.name+" floor is "+fixed(floor,4)+" mm (finer than the fab can produce)");}}
    return r;
}
std::string ManufacturingFabResult::report()const{
    std::ostringstream o;o.imbue(std::locale::classic());o<<"FAB PROFILE GATE  ("<<profile.name<<")\n  source: "<<profile.source<<"\n\n  "<<std::left<<std::setw(18)<<"metric"<<' '<<std::right<<std::setw(14)<<"board demands"<<' '<<std::setw(12)<<"fab floor"<<"   verdict\n  "<<std::string(58,'-');
    for(const auto& [label,v,floor,pass]:rows)o<<"\n  "<<std::left<<std::setw(18)<<label<<' '<<std::right<<std::setw(14)<<(v?fixed(*v,4)+" mm":"n/a")<<' '<<std::setw(9)<<fixed(floor,4)<<" mm   "<<(pass?"PASS":"FAIL (finer than fab)");
    o<<"\n\n  segments "<<demand.n_segments<<", vias "<<demand.n_vias<<", drilled holes "<<demand.n_drills;
    if(demand.pro_via_annular_mm)o<<"\n  (.kicad_pro min_via_annular_width DRC floor: "<<fixed(*demand.pro_via_annular_mm,4)<<" mm — permissive rule, not what the board emits)";
    o<<"\n\n  VERDICT: "<<(ok?"PASS":"FAIL")<<" — "<<(ok?"every demanded feature is at or above the fab floor":"the board demands geometry finer than the fab can produce");
    if(!errors.empty()){o<<'\n';for(const auto& e:errors)o<<"\n  FAIL: "<<e;}return o.str();
}
} // namespace schgen
