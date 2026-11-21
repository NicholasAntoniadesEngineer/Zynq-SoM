#include "schgen/stackup.hpp"
#include "schgen/fabricator.hpp"
#include "schgen/manufacturing_checks.hpp"
#include "manufacturing_exports_internal.hpp"
#include <functional>
#include <map>
#include <set>

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
namespace {
const std::string kind_annular="pad annular",kind_npth="npth drill",kind_slot_width="slot width",kind_slot_ratio="slot ratio",kind_silk_height="silk text height",kind_silk_line="silk stroke";
const double fab_tolerance=1e-6;
const std::size_t offender_samples=3;
const std::size_t detail_limit=24;
const std::set<std::string> text_tags{"gr_text","fp_text","property"};
const std::set<std::string> line_tags{"gr_line","fp_line","gr_arc","fp_arc","gr_rect","fp_rect","gr_circle","fp_circle","gr_poly","fp_poly","gr_curve","fp_curve"};
const std::string silk_suffix=".SilkS";
std::optional<std::string> symbol_at(const SexprList& a,std::size_t i){if(i<a.size()&&std::holds_alternative<Sexpr::Sym>(a[i].v))return std::get<Sexpr::Sym>(a[i].v).name;return std::nullopt;}
std::optional<std::string> string_at(const SexprList& a,std::size_t i){if(i<a.size()&&std::holds_alternative<std::string>(a[i].v))return std::get<std::string>(a[i].v);return std::nullopt;}
std::string head_of(const Sexpr& n){const auto* a=list(n);if(!a||a->empty())return {};return symbol_at(*a,0).value_or("");}
std::string owner_of(const Sexpr& footprint){const auto* a=list(footprint);if(a)for(const auto& child:*a){const auto* c=list(child);if(!c)continue;const auto head=head_of(child);
    if(head=="property"&&string_at(*c,1)==std::string("Reference"))return string_at(*c,2).value_or("");
    if(head=="fp_text"&&symbol_at(*c,1)==std::string("reference"))return string_at(*c,2).value_or("");}
    return "";}
std::string layer_of(const Sexpr& n){if(const auto* l=sub(n,"layer"))return string_at(*l,1).value_or("");return "";}
const SexprList* subl(const SexprList* a,const std::string& key){if(a)for(const auto& v:*a)if(tag(v,key))return list(v);return nullptr;}
bool hides(const SexprList* a){if(a)for(const auto& child:*a){if(const auto name=std::get_if<Sexpr::Sym>(&child.v)){if(name->name=="hide")return true;continue;}
    if(head_of(child)!="hide")continue;const auto* h=list(child);if(h->size()<2||symbol_at(*h,1)!=std::string("no"))return true;}
    return false;}
bool filled(const Sexpr& n){const auto* f=sub(n,"fill");if(!f||f->size()<2)return false;const auto mode=symbol_at(*f,1);return mode&&*mode!="none"&&*mode!="no";}
bool hidden(const Sexpr& n){return hides(list(n))||hides(sub(n,"effects"));}
std::string text_of(const Sexpr& n){const auto* a=list(n);if(!a)return "";const std::string head=head_of(n);const std::size_t at=head=="gr_text"?1:2;std::string t=string_at(*a,at).value_or("");if(t.size()>detail_limit)t.resize(detail_limit);return t;}
void keep_min(std::optional<double>& slot,double v){if(!slot||v<*slot)slot=v;}
void scan_pad(const Sexpr& pad,const std::string& owner,ManufacturingBoardDemand& d){
    const auto* a=list(pad);if(!a)return;const std::string type=symbol_at(*a,2).value_or("");const auto* dr=sub(pad,"drill");if(!dr)return;
    std::vector<double> dims;bool oval=false;for(std::size_t i=1;i<dr->size();++i){if(std::holds_alternative<double>((*dr)[i].v))dims.push_back(std::get<double>((*dr)[i].v));else if(symbol_at(*dr,i)==std::string("oval"))oval=true;}
    if(dims.empty()||*std::min_element(dims.begin(),dims.end())<=0)return;
    const double least=*std::min_element(dims.begin(),dims.end()),most=*std::max_element(dims.begin(),dims.end());
    if(type=="np_thru_hole"){if(!oval){keep_min(d.min_npth_drill_mm,least);d.items.push_back({kind_npth,owner,"",least});}return;}
    if(type!="thru_hole")return;
    if(const auto* sz=sub(pad,"size");sz&&sz->size()>2&&std::holds_alternative<double>((*sz)[1].v)&&std::holds_alternative<double>((*sz)[2].v)){
        const double ring=decimal_round((std::min(std::get<double>((*sz)[1].v),std::get<double>((*sz)[2].v))-least)/2,6);keep_min(d.min_pad_annular_mm,ring);d.items.push_back({kind_annular,owner,string_at(*a,1).value_or(""),ring});}
    if(oval){keep_min(d.min_slot_width_mm,least);keep_min(d.min_slot_ratio,most/least);d.items.push_back({kind_slot_width,owner,string_at(*a,1).value_or(""),least});d.items.push_back({kind_slot_ratio,owner,string_at(*a,1).value_or(""),decimal_round(most/least,6)});}
}
void scan_silk(const Sexpr& n,const std::string& owner,ManufacturingBoardDemand& d){
    const std::string head=head_of(n),layer=layer_of(n);if(layer.size()<silk_suffix.size()||layer.compare(layer.size()-silk_suffix.size(),silk_suffix.size(),silk_suffix)!=0)return;
    if(text_tags.count(head)){if(hidden(n))return;const auto* f=subl(sub(n,"effects"),"font");if(!f)return;
        if(const auto* sz=subl(f,"size");sz&&sz->size()>2&&std::holds_alternative<double>((*sz)[2].v)){const double h=std::get<double>((*sz)[2].v);keep_min(d.min_silk_height_mm,h);d.items.push_back({kind_silk_height,owner,text_of(n),h});}
        if(const auto* th=subl(f,"thickness");th&&th->size()>1&&std::holds_alternative<double>((*th)[1].v)){const double t=std::get<double>((*th)[1].v);keep_min(d.min_silk_line_mm,t);d.items.push_back({kind_silk_line,owner,"text "+text_of(n),t});}return;}
    if(line_tags.count(head)&&!filled(n))if(const auto* st=sub(n,"stroke"))if(const auto* w=subl(st,"width");w&&w->size()>1&&std::holds_alternative<double>((*w)[1].v)){const double t=std::get<double>((*w)[1].v);keep_min(d.min_silk_line_mm,t);d.items.push_back({kind_silk_line,owner,head,t});}
}
void scan_board(const Sexpr& n,const std::string& owner,ManufacturingBoardDemand& d){
    const auto* a=list(n);if(!a)return;
    for(const auto& child:*a){if(!list(child)||list(child)->empty())continue;const std::string head=head_of(child);
        if(head=="footprint"){scan_board(child,owner_of(child),d);continue;}
        if(head=="pad")scan_pad(child,owner,d);
        else if(text_tags.count(head)||line_tags.count(head))scan_silk(child,owner,d);
        scan_board(child,owner,d);}
}
}
ManufacturingMinimums manufacturing_fab_minimums(){const auto& f=board_fabrication();return {f.outer_value(fabricator_key::trace),f.outer_value(fabricator_key::space)};}
ManufacturingFabProfile manufacturing_fab_profile(){const auto& f=board_fabrication();const auto& p=f.profile;const auto& lead=p.at("fab.by_copper_oz."+fabricator_copper_key(f.config.outer_oz)+"."+fabricator_key::trace);
    std::ostringstream name;name<<p.name<<" "<<(f.config.assembly_service)<<" "<<board_stackup().copper.size()<<"-layer ("<<fabricator_copper_key(f.config.outer_oz)<<"oz)";
    return {name.str(),f.outer_value(fabricator_key::trace),f.outer_value(fabricator_key::space),p.number(fabricator_key::via_hole_min),p.number(fabricator_key::via_diameter_min),p.number(fabricator_key::via_over_hole_preferred)/2,p.number(fabricator_key::hole_pad),
        f.outer_value(fabricator_key::annular_min),p.number(fabricator_key::npth_min),p.number(fabricator_key::slot_width_min),p.number(fabricator_key::slot_ratio_min),p.number(fabricator_key::silk_height),p.number(fabricator_key::silk_line),
        lead.source_url+", read "+lead.read_utc};}
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
    d.min_hole_to_hole_mm=rule(project,"\"min_hole_to_hole\"\\s*:\\s*"+number,true);scan_board(pcb,"",d);return d;
}
ManufacturingBoardDemand measure_manufacturing_board(const std::filesystem::path& pcb,const std::filesystem::path& dru,const std::filesystem::path& project){
    if(!std::filesystem::exists(pcb))return {};
    return measure_manufacturing_board(sexpr_loads(read(pcb)),std::filesystem::exists(dru)?read(dru):"",std::filesystem::exists(project)?read(project):"");
}
ManufacturingFabResult check_manufacturing_fab(const ManufacturingBoardDemand& d,const ManufacturingFabProfile& p){
    ManufacturingFabResult r;r.profile=p;r.demand=d;
    const std::string mm_unit="mm",ratio_unit="x";
    for(const auto& [label,v,floor,unit,kind]:std::vector<std::tuple<std::string,std::optional<double>,double,std::string,std::string>>{
        {"min trace width",d.min_trace_mm,p.min_trace_mm,mm_unit,""},{"min clearance",d.min_clearance_mm,p.min_clearance_mm,mm_unit,""},{"min drill",d.min_drill_mm,p.min_drill_mm,mm_unit,""},{"min via diameter",d.min_via_dia_mm,p.min_via_dia_mm,mm_unit,""},{"min via annular",d.min_via_annular_mm,p.min_via_annular_mm,mm_unit,""},{"min hole-to-hole rule",d.min_hole_to_hole_mm,p.min_hole_to_hole_mm,mm_unit,""},
        {"min PTH pad annular",d.min_pad_annular_mm,p.min_pad_annular_mm,mm_unit,kind_annular},{"min NPTH drill",d.min_npth_drill_mm,p.min_npth_drill_mm,mm_unit,kind_npth},{"min plated slot width",d.min_slot_width_mm,p.min_slot_width_mm,mm_unit,kind_slot_width},{"min plated slot ratio",d.min_slot_ratio,p.min_slot_ratio,ratio_unit,kind_slot_ratio},
        {"min silk text height",d.min_silk_height_mm,p.min_silk_height_mm,mm_unit,kind_silk_height},{"min silk stroke",d.min_silk_line_mm,p.min_silk_line_mm,mm_unit,kind_silk_line}}){
        bool ok=!v||*v>=floor-fab_tolerance;r.rows.push_back({label,v,floor,ok,unit,kind});if(!ok){r.ok=false;r.errors.push_back(label+": board demands "+fixed(*v,4)+" "+unit+" but "+p.name+" floor is "+fixed(floor,4)+" "+unit+" (finer than the fab can produce)");}}
    return r;
}
std::string ManufacturingFabResult::report()const{
    std::ostringstream o;o.imbue(std::locale::classic());o<<"FAB PROFILE GATE  ("<<profile.name<<")\n  source: "<<profile.source<<"\n\n  "<<std::left<<std::setw(24)<<"metric"<<' '<<std::right<<std::setw(14)<<"board demands"<<' '<<std::setw(12)<<"fab floor"<<"   verdict\n  "<<std::string(64,'-');
    for(const auto& row:rows)o<<"\n  "<<std::left<<std::setw(24)<<row.label<<' '<<std::right<<std::setw(14)<<(row.value?fixed(*row.value,4)+" "+row.unit:"n/a")<<' '<<std::setw(9)<<fixed(row.floor,4)<<" "<<row.unit<<"   "<<(row.pass?"PASS":"FAIL (finer than fab)");
    o<<"\n\n  segments "<<demand.n_segments<<", vias "<<demand.n_vias<<", drilled holes "<<demand.n_drills;
    if(demand.pro_via_annular_mm)o<<"\n  (.kicad_pro min_via_annular_width DRC floor: "<<fixed(*demand.pro_via_annular_mm,4)<<" mm — permissive rule, not what the board emits)";
    for(const auto& row:rows){if(row.pass||row.kind.empty())continue;
        std::map<std::pair<double,std::string>,std::vector<const ManufacturingFabItem*>> groups;
        for(const auto& item:demand.items)if(item.kind==row.kind&&item.value<row.floor-fab_tolerance)groups[{item.value,item.detail}].push_back(&item);
        o<<"\n\n  below the floor, "<<row.label<<":";
        for(const auto& [key,items]:groups){o<<"\n    "<<fixed(key.first,6)<<" "<<row.unit<<" x"<<items.size()<<(key.second.empty()?"":"  '"+key.second+"'")<<"  e.g.";std::size_t shown=0;std::set<std::string> seen;
            for(const auto* item:items){if(shown>=offender_samples)break;if(!seen.insert(item->owner+"/"+item->detail).second)continue;o<<' '<<(item->owner.empty()?"board":item->owner);++shown;}}}
    o<<"\n\n  VERDICT: "<<(ok?"PASS":"FAIL")<<" — "<<(ok?"every demanded feature is at or above the fab floor":"the board demands geometry finer than the fab can produce");
    if(!errors.empty()){o<<'\n';for(const auto& e:errors)o<<"\n  FAIL: "<<e;}return o.str();
}
} // namespace schgen
