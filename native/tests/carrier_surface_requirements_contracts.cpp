#include "schgen/project_authoring.hpp"
#include "schgen/pcb_checks.hpp"
#include "schgen/pcb_placement_gates.hpp"
#include "schgen/placement_requirements.hpp"
#include <algorithm>
#include <iostream>
#include <tuple>

namespace {
using namespace schgen;
using Pins = std::map<std::pair<std::string, std::string>, std::string>;
std::size_t checks = 0;
void require(bool ok, const std::string& why) {
    ++checks;
    if (!ok) throw std::runtime_error(why);
}
const JsonNode& field(const JsonNode& j, const std::string& key) {
    auto p = object_field(j, key);
    if (!p) throw std::runtime_error("missing requirement " + key);
    return *p;
}
std::string text(const JsonNode& j, const std::string& key) {
    const auto& v = field(j, key);
    if (v.kind != JsonKind::String) throw std::runtime_error("non-string " + key);
    return v.string_value;
}
Pins pins(const CircuitSheetIr& c) {
    Pins out;
    for (const auto& n : c.nets) for (const auto& p : n.pins)
        require(out.emplace(std::make_pair(p.ref,p.pin),n.name).second, "duplicate pin identity");
    return out;
}
using Ownership = std::tuple<std::string,std::string,std::string,std::string,std::string>;
const std::map<std::string,std::vector<Ownership>> expected{
    {"board_aux", {{"U1","5","C1","+3V3","10u"},
                   {"U1","1","C2","+3V3_AUX","100n"},
                   {"U1","1","C3","+3V3_AUX","10u"},
                   {"U2","2","C4","+3V3_SC","100n"},
                   {"U2","7","C5","+3V3_AUX","100n"}}},
    {"bringup_rails", {{"U1","24","C1","+3V3_SC","100n"}}}
};
// Test-only requirements verification, NOT a replacement runtime placement gate.
// Exact ownership is independently fixed from the live construction operations;
// mere shared-rail membership cannot distinguish C2 from C5.
void validate(const CircuitSheetIr& c, const JsonNode& req) {
    require(text(req,"sheet") == c.name, "sheet identity");
    const auto& rows = field(req,"ownership").array_value;
    const auto& want = expected.at(c.name);
    require(rows.size() == want.size(), "omitted or extra ownership");
    const auto nets = pins(c);
    std::set<Ownership> actual;
    for (const auto& r : rows) {
        auto owner=text(r,"owner"), pin=text(r,"pin"), cap=text(r,"cap");
        auto rail=text(r,"rail"), value=text(r,"value");
        require(text(r,"cap_pin")=="1" && text(r,"return_pin")=="2" && text(r,"return_net")=="GND", "capacitor terminal identity");
        require(nets.at({owner,pin})==rail && nets.at({cap,"1"})==rail && nets.at({cap,"2"})=="GND", "supply/return topology");
        auto part=std::find_if(c.parts.begin(),c.parts.end(),[&](const auto& p){return p.ref==cap;});
        require(part!=c.parts.end() && part->value==value && part->lib_id=="Device:C", "capacitor type/value");
        auto ic=std::find_if(c.parts.begin(),c.parts.end(),[&](const auto& p){return p.ref==owner;});
        require(ic!=c.parts.end(), "owner exists");
        const auto named=std::find_if(ic->pin_names.begin(),ic->pin_names.end(),[&](const auto& n){return n.name==text(r,"pin_name");});
        require(named!=ic->pin_names.end() && std::find(named->numbers.begin(),named->numbers.end(),pin)!=named->numbers.end(), "physical pin/name binding");
        require(actual.emplace(owner,pin,cap,rail,value).second, "duplicate ownership");
    }
    require(actual==std::set<Ownership>(want.begin(),want.end()), "wrong owner/member assignment");
    require(field(field(req,"proximity"),"numeric_limit_mm").kind==JsonKind::Null, "no invented proximity threshold");
}
template<class F> void rejects(F f, const std::string& why) {
    bool rejected=false;
    try { f(); } catch (const std::exception&) { rejected=true; }
    require(rejected, "mutation escaped: " + why);
}
JsonNode& mutable_field(JsonNode& n,const std::string& key) {
    for(auto& kv:n.object_value) if(kv.first==key) return kv.second;
    throw std::runtime_error("missing mutation key");
}
Pins model_pins(const PcbCheckModel& m) {
    Pins out;
    for(const auto& i:m.insts) for(const auto& p:i.pad_nets) out[{i.ref,p.first}]=p.second.second;
    return out;
}
void runtime_checks(const CircuitSheetIr& circuit,const JsonNode& manifest,PcbCheckModel model) {
    const auto r=parse_placement_requirements(manifest);
    const auto d=carrier_surface_requirement_declaration(circuit.name);
    std::map<std::string,CatalogPart> catalog;
    for(const auto& entry:d.owner_mpn) catalog.emplace(entry.second,lookup_part_catalog(entry.second));
    std::map<std::string,std::string> refs,nets;
    for(const auto& n:circuit.nets) nets.emplace(n.name,"hierarchy/"+n.name);
    int net_id=1;
    for(const auto& n:nets) model.net_numbers.emplace(n.second,net_id++);
    // Synthetic geometry is an independent distance oracle, not a placement
    // prescription or whole-board proof. The owned cap pad has gap (3,4),
    // hence 5 mm; its return pad overlaps the owner to catch nearest-any-pad.
    for(auto& i:model.insts) {
        refs.emplace(i.ref,"board_"+i.ref);i.ref="board_"+i.ref;
        std::string fp="(footprint \"oracle\" (layer \"F.Cu\")";
        for(auto& pn:i.pad_nets) {
            pn.second.second=nets.at(pn.second.second);
            pn.second.first=model.net_numbers.at(pn.second.second);
            const bool owned=i.ref.rfind("board_C",0)==0&&pn.first=="1";
            fp+=" (pad \""+pn.first+"\" smd rect (at "+(owned?std::string("4 5"):std::string("0 0"))+") (size 1 1) (layers \"F.Cu\" \"F.Paste\" \"F.Mask\"))";
        }
        fp+=")";
        i.mod=pcb_check_footprint("synthetic-owned-terminal-oracle",fp);
    }
    auto check=[&](const PlacementRequirements& policy,const CircuitSheetIr& c,const PcbCheckModel& m){
        return check_placement_requirements(policy,d,c,catalog,PcbCheckInput(m),refs,nets);
    };
    auto good=check(r,circuit,model);
    require(good.hard_requirements_met(),good.summary());
    require(good.status()=="UNVERIFIED"&&!good.unverified.empty(),"qualitative requirements must never PASS");
    require(good.measurements.size()==r.ownership.size(),"each owned terminal measured");
    for(const auto& measurement:good.measurements) require(measurement.planar_pad_box_gap_mm==5.,"3-4-5 owned-terminal distance oracle");
    for(std::size_t i=0;i<r.ownership.size();++i) {
        auto missing=r;missing.ownership.erase(missing.ownership.begin()+static_cast<std::ptrdiff_t>(i));
        require(!check(missing,circuit,model).hard_requirements_met(),"runtime omitted ownership rejection");
        auto wrong=r;wrong.ownership[i].cap="C999";
        require(!check(wrong,circuit,model).hard_requirements_met(),"runtime wrong member rejection");
        auto detached=model;
        auto member=std::find_if(detached.insts.begin(),detached.insts.end(),[&](const auto& p){return p.ref==refs.at(r.ownership[i].cap);});
        member->pad_nets.at("2").second="wrong-return";
        require(!check(r,circuit,detached).hard_requirements_met(),"runtime changed actual return net");
        auto badvalue=circuit;
        for(auto& p:badvalue.parts) if(p.ref==r.ownership[i].cap) p.value="1p";
        auto candidate=model;
        for(auto& p:candidate.insts) if(p.ref==refs.at(r.ownership[i].cap)) p.value="1p";
        require(!check(r,badvalue,candidate).hard_requirements_met(),"runtime independent expected value");
    }
    if(circuit.name=="board_aux") {
        auto swapped=r;std::swap(swapped.ownership[1].cap,swapped.ownership[4].cap);
        require(!check(swapped,circuit,model).hard_requirements_met(),"runtime same-rail wrong owner");
    }
    for(const auto& sw:r.top_switches) {
        auto moved=model;for(auto& p:moved.insts) if(p.ref==refs.at(sw)) p.side="bottom";
        require(!check(r,circuit,moved).hard_requirements_met(),"runtime actual model access rejection");
        require(model_pins(moved)==model_pins(model),"runtime side mutation preserves pin nets");
        auto missing=r;missing.top_switches.erase(sw);
        require(!check(missing,circuit,model).hard_requirements_met(),"runtime omitted switch declaration");
    }
    auto wrong_catalog=catalog;
    wrong_catalog.begin()->second.pins.clear();
    require(!check_placement_requirements(r,d,circuit,wrong_catalog,PcbCheckInput(model),refs,nets).hard_requirements_met(),"independent catalog pin identity");
    auto duplicate_physical=catalog;
    const auto& owned=r.ownership.front();
    duplicate_physical.at(d.owner_mpn.at(owned.owner)).pins.push_back({owned.pin,"DIFFERENT_NAME","passive"});
    require(!check_placement_requirements(r,d,circuit,duplicate_physical,PcbCheckInput(model),refs,nets).hard_requirements_met(),"duplicate physical catalog pin with another name is ambiguous");
    auto wrong_ref=refs;wrong_ref.begin()->second="missing";
    require(!check_placement_requirements(r,d,circuit,catalog,PcbCheckInput(model),wrong_ref,nets).hard_requirements_met(),"missing mapped placed identity");
    auto changed=model;changed.insts.front().pad_nets.begin()->second.second="wrong-net";
    require(!check(r,circuit,changed).hard_requirements_met(),"all pin identities checked, not only owned caps");
    changed=model;changed.insts.front().pad_nets.begin()->second.first=0;
    require(!check(r,circuit,changed).hard_requirements_met(),"numeric net identity checked independently of name");
    auto side_change=model;
    for(auto& i:side_change.insts) if(i.ref==refs.at(r.ownership.front().cap)) i.side="bottom";
    auto side_report=check(r,circuit,side_change);
    require(side_report.status()=="UNVERIFIED"&&side_report.measurements.front().member_side=="bottom", "opposite-side capacitor is reported, not granted placement approval");
    auto unresolved=model;unresolved.insts.clear();
    require(!check(r,circuit,unresolved).hard_requirements_met(),"empty placed model fails");
    auto unknown=manifest;
    mutable_field(mutable_field(unknown,"proximity"),"numeric_limit_mm").kind=JsonKind::Number;
    rejects([&]{(void)parse_placement_requirements(unknown);},"numeric policy cannot silently enter qualitative checker");
    auto no_geometry=model;for(auto& p:no_geometry.insts) p.mod.reset();
    require(!check(r,circuit,no_geometry).hard_requirements_met(),"missing owned-terminal geometry fails");
    auto duplicate=manifest;
    auto& rows=mutable_field(duplicate,"ownership").array_value; rows.push_back(rows.front());
    rejects([&]{(void)parse_placement_requirements(duplicate);},"duplicate manifest ownership");
    auto bad_owner=circuit;auto bad_owner_model=model;
    for(auto& p:bad_owner.parts) if(p.ref==r.ownership.front().owner) p.value="substituted-owner";
    for(auto& p:bad_owner_model.insts) if(p.ref==refs.at(r.ownership.front().owner)) p.value="substituted-owner";
    require(!check(r,bad_owner,bad_owner_model).hard_requirements_met(),"owner value checked against independent catalog");
}
void exercise(const std::filesystem::path& root, const std::string& sheet,
              const std::filesystem::path& assets) {
    ProjectAuthoringInput input; input.context=make_authoring_context(root);
    const auto c=author_project_subsystem("carrier",sheet,input);
    const auto original=pins(c);
    require(original==pins(load_circuit_json(assets/"carrier/subsystems"/sheet/"circuit.json")), "live/frozen pin-net identities differ");
    const auto req=parse_json_file((assets/"carrier/subsystems"/sheet/"placement_requirements.json").string());
    validate(c,req);
    for(std::size_t i=0;i<expected.at(sheet).size();++i) {
        auto omitted=req; auto& rows=mutable_field(omitted,"ownership").array_value;
        rows.erase(rows.begin()+static_cast<std::ptrdiff_t>(i));
        rejects([&]{validate(c,omitted);},"omitted ownership");
        auto broken=c;
        const auto cap=std::get<2>(expected.at(sheet)[i]);
        for(auto& n:broken.nets) for(auto& p:n.pins) if(p.ref==cap && p.pin=="2") p.pin="missing_return";
        rejects([&]{validate(broken,req);},"missing grounded return");
    }
    auto wrong=req;
    mutable_field(mutable_field(wrong,"ownership").array_value.front(),"cap").string_value=sheet=="board_aux"?"C4":"C2";
    rejects([&]{validate(c,wrong);},"wrong rail member");
    if(sheet=="board_aux") {
        auto swapped=req; auto& rows=mutable_field(swapped,"ownership").array_value;
        std::swap(mutable_field(rows[1],"cap"),mutable_field(rows[4],"cap"));
        rejects([&]{validate(c,swapped);},"same-rail same-value wrong owner");
    }
    PcbCheckModel model; model.board_w=100; model.board_h=100;
    for(const auto& p:c.parts) {
        PcbCheckInstance instance; instance.ref=p.ref; instance.value=p.value;
        instance.footprint=p.footprint; instance.sheet=sheet;
        for(const auto& n:original) if(n.first.first==p.ref) instance.pad_nets[n.first.second]={1,n.second};
        model.insts.push_back(std::move(instance));
    }
    require(check_placement_mech(PcbCheckInput(model)).face_top_on_bottom.empty(),"baseline top-face switches");
    // Negative capability proof: a requirements-only object must not be
    // advertised as a useful live placement contract merely because it passes.
    const auto unsupported=check_pcb_placement_contract(PcbCheckInput(model),sheet,&req,{});
    require(unsupported.ok && unsupported.checked==0,
            "engine capability changed: review requirements promotion explicitly");
    const auto& access=field(field(req,"access"),"top_face_switches").array_value;
    require(access.size()==(sheet=="board_aux"?1:6),"switch requirement count");
    std::set<std::string> seen;
    for(const auto& r:access) {
        require(seen.insert(r.string_value).second,"duplicate access member");
        auto moved=model;
        auto it=std::find_if(moved.insts.begin(),moved.insts.end(),[&](const auto& p){return p.ref==r.string_value;});
        require(it!=moved.insts.end() && it->ref.rfind("SW",0)==0,"switch access subject");
        it->side="bottom"; it->x=23; it->y=31; it->rotation=180;
        require(!check_placement_mech(PcbCheckInput(moved)).face_top_on_bottom.empty(),"existing mechanical gate rejects bottom switch");
        require(model_pins(moved)==original,"pose/side mutation preserved every pin-net identity");
    }
    require(pins(c)==original,"requirements validation never changes electrical design");
    runtime_checks(c,req,model);
}
}
int main(int argc,char** argv) {
    try {
        require(argc==3||argc==4,"usage: carrier_surface_requirements_contracts REPOSITORY CATALOG [BOARD_AUX_ASSET_ROOT]");
        require(open_part_catalog(argv[2]),"open read-only native catalog");
        exercise(argv[1],"board_aux",argc==4?argv[3]:argv[1]); exercise(argv[1],"bringup_rails",argv[1]);
        close_part_catalog();
        std::cout<<"PASS "<<checks<<" requirements assertions; runtime ownership/top-face checked, qualitative proximity/access-envelope UNVERIFIED\n";
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
