#include "schgen/placement_requirements.hpp"
#include <algorithm>
#include <cmath>
#include <sstream>
#include <tuple>

namespace schgen {
namespace {
auto key(const SupplyOwnership& r) {
    return std::tie(r.owner,r.pin,r.pin_name,r.cap,r.cap_pin,r.return_pin,r.rail,r.return_net,r.value,r.role);
}
void demand(bool v,const std::string& why) { if(!v) throw std::runtime_error(why); }
const JsonNode& field(const JsonNode& n,const std::string& k,JsonKind type) {
    auto p=object_field(n,k); demand(p && p->kind==type,"missing or mistyped requirement: "+k);return *p;
}
std::string str(const JsonNode& n,const std::string& k) {
    auto s=field(n,k,JsonKind::String).string_value; demand(!s.empty(),"empty requirement: "+k);return s;
}
void keys(const JsonNode& n,const std::set<std::string>& allowed) {
    demand(n.kind==JsonKind::Object,"requirement object expected");
    std::set<std::string> seen;
    for(const auto& kv:n.object_value) demand(allowed.count(kv.first)&&seen.insert(kv.first).second,"unknown/duplicate requirement key: "+kv.first);
}
using Pin=std::pair<std::string,std::string>;
using Nets=std::map<Pin,std::string>;
double gap(const Box4& a,const Box4& b) {
    for(const auto* box:{&a,&b}) demand(std::isfinite(box->x0)&&std::isfinite(box->y0)&&std::isfinite(box->x1)&&std::isfinite(box->y1)&&box->x0<=box->x1&&box->y0<=box->y1,"invalid owned-terminal box");
    const double dx=std::max({0.,a.x0-b.x1,b.x0-a.x1});
    const double dy=std::max({0.,a.y0-b.y1,b.y0-a.y1});
    const double d=std::hypot(dx,dy); demand(std::isfinite(d),"owned-terminal distance overflow");return d;
}
}
bool SupplyOwnership::operator==(const SupplyOwnership& b) const {return key(*this)==key(b);}
PlacementRequirements parse_placement_requirements(const JsonNode& n) {
    keys(n,{"schema","sheet","status","ownership","access","proximity","side","sources"});
    demand(str(n,"schema")=="schgen.placement-requirements/1","unsupported requirement schema");
    PlacementRequirements r; r.sheet=str(n,"sheet");
    const auto& proximity=field(n,"proximity",JsonKind::Object);
    keys(proximity,{"numeric_limit_mm","status"});
    (void)field(proximity,"numeric_limit_mm",JsonKind::Null);
    (void)str(proximity,"status");
    for(const auto& j:field(n,"ownership",JsonKind::Array).array_value) {
        keys(j,{"owner","pin","pin_name","cap","cap_pin","return_pin","rail","return_net","value","role"});
        SupplyOwnership o{str(j,"owner"),str(j,"pin"),str(j,"pin_name"),str(j,"cap"),str(j,"cap_pin"),str(j,"return_pin"),str(j,"rail"),str(j,"return_net"),str(j,"value"),str(j,"role")};
        demand(std::none_of(r.ownership.begin(),r.ownership.end(),[&](const auto& p){return p.cap==o.cap;}),"duplicate capacitor ownership");
        r.ownership.push_back(std::move(o));
    }
    demand(!r.ownership.empty(),"empty supply ownership");
    const auto& access=field(n,"access",JsonKind::Object);
    keys(access,{"top_face_switches","actuation_envelope"});
    (void)str(access,"actuation_envelope");
    for(const auto& s:field(access,"top_face_switches",JsonKind::Array).array_value)
        demand(s.kind==JsonKind::String&&!s.string_value.empty()&&r.top_switches.insert(s.string_value).second,"invalid/duplicate access subject");
    return r;
}
PlacementRequirementDeclaration carrier_surface_requirement_declaration(const std::string& sheet) {
    PlacementRequirementDeclaration d;d.required.sheet=sheet;
    if(sheet=="board_aux") {
        d.owner_mpn={{"U1","SY6280AAC"},{"U2","PCA9306DCUR"}};
        d.required.ownership={
            {"U1","5","IN","C1","1","2","+3V3","GND","100n","input_bypass"},
            {"U1","1","OUT","C2","1","2","+3V3_AUX","GND","100n","output_bypass"},
            {"U1","1","OUT","C3","1","2","+3V3_AUX","GND","10u","shared_output_bulk"},
            {"U2","2","VREF1","C4","1","2","+3V3_SC","GND","100n","authored_reference_rail_bypass_not_translation_filter"},
            {"U2","7","VREF2","C5","1","2","+3V3_AUX","GND","100n","authored_reference_rail_bypass_not_translation_filter"}};
        d.required.top_switches={"SW1"};
    } else if(sheet=="bringup_rails") {
        d.owner_mpn={{"U1","TCA9535PWR"}};
        d.required.ownership={{"U1","24","VCC","C1","1","2","+3V3_SC","GND","100n","supply_bypass"}};
        d.required.top_switches={"SW1","SW2","SW3","SW4","SW5","SW6"};
    } else throw std::runtime_error("no reviewed carrier surface requirements for "+sheet);
    return d;
}
PlacementRequirementReport check_placement_requirements(
    const PlacementRequirements& r,const PlacementRequirementDeclaration& d,
    const CircuitSheetIr& circuit,const std::map<std::string,CatalogPart>& catalog,
    const PcbCheckInput& placed,const std::map<std::string,std::string>& refs,
    const std::map<std::string,std::string>& nets) {
    PlacementRequirementReport out;out.sheet=r.sheet;
    out.unverified={"Qualitative near-pin placement: no reviewed numeric maximum; measurement is not acceptance.",
                    "Actuation/access envelope and assembly obstruction clearance unverified.",
                    "No new movement/side permission; preserve all existing placement gates and restrictions."};
    try {
        demand(!d.required.ownership.empty(),"independent declaration is empty");
        demand(r.sheet==circuit.name&&r.sheet==d.required.sheet,"requirement/live/declaration sheet mismatch");
        auto a=r.ownership,b=d.required.ownership;
        auto less=[](const auto& x,const auto& y){return key(x)<key(y);};
        std::sort(a.begin(),a.end(),less);std::sort(b.begin(),b.end(),less);
        demand(a==b,"omitted, extra or wrong ownership declaration");
        demand(r.top_switches==d.required.top_switches,"omitted, extra or wrong access declaration");
        std::map<std::string,const CircuitPartIr*> parts;
        for(const auto& p:circuit.parts) demand(parts.emplace(p.ref,&p).second,"duplicate live reference");
        Nets live;
        std::set<std::string> live_net_names, mapped_nets, mapped_refs;
        for(const auto& n:circuit.nets) {
            demand(live_net_names.insert(n.name).second,"duplicate live net");
            auto it=nets.find(n.name); demand(it!=nets.end()&&!it->second.empty()&&mapped_nets.insert(it->second).second,"missing/aliased trusted net mapping");
            for(const auto& p:n.pins) demand(parts.count(p.ref)&&live.emplace(Pin{p.ref,p.pin},n.name).second,"unknown or multiply-netted live pin");
        }
        demand(nets.size()==live_net_names.size()&&refs.size()==parts.size(),"incomplete/extra trusted identity mapping");
        const auto& model=placed.model();std::map<std::string,std::size_t> indices;
        std::set<int> net_ids;
        for(const auto& n:mapped_nets) {
            auto id=model.net_numbers.find(n);
            demand(id!=model.net_numbers.end()&&id->second>0&&net_ids.insert(id->second).second,"missing/aliased placed net-number identity");
        }
        for(std::size_t i=0;i<model.insts.size();++i)
            demand(indices.emplace(model.insts[i].ref,i).second,"duplicate placed reference");
        for(const auto& p:parts) {
            auto ref=refs.find(p.first);demand(ref!=refs.end()&&mapped_refs.insert(ref->second).second,"missing/aliased trusted ref mapping");
            auto idx=indices.find(ref->second);demand(idx!=indices.end(),"missing placed part "+p.first);
            const auto& inst=model.insts[idx->second];
            demand(inst.sheet==r.sheet&&inst.value==p.second->value&&inst.footprint==p.second->footprint,"placed identity changed: "+p.first);
            demand(inst.side=="top"||inst.side=="bottom","invalid placed side");
            for(const auto& pin:live) if(pin.first.first==p.first) {
                auto actual=inst.pad_nets.find(pin.first.second);
                const auto& name=nets.at(pin.second);
                demand(actual!=inst.pad_nets.end()&&actual->second.second==name&&actual->second.first==model.net_numbers.at(name),"placed pin/net changed: "+p.first+"."+pin.first.second);
            }
            for(const auto& pad:inst.pad_nets) if(!live.count({p.first,pad.first}))
                demand(pad.second.first==0&&(pad.second.second.empty()||pad.second.second.rfind("unconnected-",0)==0),"unexpected connected placed pad: "+p.first+"."+pad.first);
        }
        for(const auto& inst:model.insts) if(inst.sheet==r.sheet)
            demand(mapped_refs.count(inst.ref),"unexpected placed sheet part");
        for(const auto& o:r.ownership) {
            demand(parts.count(o.owner)&&parts.count(o.cap),"missing owner/cap part");
            const auto& owner=*parts.at(o.owner);const auto& cap=*parts.at(o.cap);
            const auto mpn=d.owner_mpn.at(o.owner);const auto& part=catalog.at(mpn);
            demand(part.mpn==mpn&&owner.value==part.mpn&&owner.lib_id==part.lib_id&&owner.footprint==part.footprint,"owner catalog identity mismatch");
            demand(std::count_if(part.pins.begin(),part.pins.end(),[&](const auto& p){return p.number==o.pin;})==1,"owner physical pin number is missing/ambiguous in independent catalog");
            const auto physical=std::find_if(part.pins.begin(),part.pins.end(),[&](const auto& p){return p.number==o.pin;});
            demand(physical->name==o.pin_name,"owner pin/name absent from independent catalog");
            demand(cap.lib_id=="Device:C"&&cap.value==o.value,"wrong capacitor type/value");
            demand(live.at({o.owner,o.pin})==o.rail&&live.at({o.cap,o.cap_pin})==o.rail&&live.at({o.cap,o.return_pin})==o.return_net,"owned supply/return topology mismatch");
            auto oi=indices.at(refs.at(o.owner)),ci=indices.at(refs.at(o.cap));
            const auto& ob=placed.geometry_at(oi).pad_boxes.at(o.pin);
            const auto& cb=placed.geometry_at(ci).pad_boxes.at(o.cap_pin);
            (void)placed.geometry_at(ci).pad_boxes.at(o.return_pin);
            out.measurements.push_back({o.owner,o.pin,o.cap,o.cap_pin,model.insts[oi].side,model.insts[ci].side,gap(ob,cb)});
        }
        for(const auto& ref:r.top_switches) {
            demand(ref.rfind("SW",0)==0&&parts.count(ref),"access subject is not a live switch");
            demand(model.insts[indices.at(refs.at(ref))].side=="top","access switch on bottom: "+ref);
        }
    } catch(const std::exception& e) {out.violations.push_back(e.what());}
    return out;
}
std::string PlacementRequirementReport::summary() const {
    std::ostringstream out;out<<"PLACEMENT REQUIREMENTS "<<sheet<<": "<<status()<<'\n';
    for(const auto& v:violations) out<<"FAIL "<<v<<'\n';
    for(const auto& m:measurements) out<<m.owner<<'.'<<m.owner_pin<<" -> "<<m.member<<'.'<<m.member_pin<<" planar_pad_box_gap_mm="<<m.planar_pad_box_gap_mm<<" sides="<<m.owner_side<<'/'<<m.member_side<<" UNVERIFIED proximity\n";
    for(const auto& v:unverified) out<<"UNVERIFIED "<<v<<'\n';
    return out.str();
}
} // namespace schgen
