// Frozen Python orchestration outputs plus independent numeric/mutation tests.
// No Python, installed footprint library, live board output, or source inspection.
#include "../src/floorplan_internal.hpp"
#include "board_policy_ledger_reference.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <limits>
#include <sstream>
#include <unistd.h>

namespace {
using namespace schgen;
using namespace schgen::floorplan_detail;
using J=JsonNode;
int checks=0;
void require(bool ok,const std::string& why) { ++checks; if (!ok) throw std::runtime_error(why); }
std::string read_bytes(const std::filesystem::path& path) {
    std::ifstream file(path,std::ios::binary);
    if(!file)throw std::runtime_error("cannot read contract file "+path.string());
    return {std::istreambuf_iterator<char>(file),{}};
}
struct TemporaryOutput {
    std::filesystem::path directory;
    TemporaryOutput() {
        auto pattern=(std::filesystem::temp_directory_path()/"floorplan-contracts.XXXXXX").string();
        if(!::mkdtemp(pattern.data()))throw std::runtime_error("cannot create private contract output");
        directory=pattern;
    }
    ~TemporaryOutput() {std::error_code ignored;std::filesystem::remove_all(directory,ignored);}
    TemporaryOutput(const TemporaryOutput&)=delete;
    TemporaryOutput& operator=(const TemporaryOutput&)=delete;
};
const J& field(const J& n,const std::string& key) {
    const auto* p=object_field(n,key); if (!p) throw std::runtime_error("missing fixture field "+key); return *p;
}
std::string str(const J& n,const std::string& key) {
    const auto* p=object_field(n,key); return p && p->kind==JsonKind::String ? p->string_value:"";
}
double num(const J& n,const std::string& key,double fallback=0) {
    const auto* p=object_field(n,key); return p && p->kind==JsonKind::Number ? p->number_value:fallback;
}
bool boolean(const J& n,const std::string& key) { const auto* p=object_field(n,key); return p && p->bool_value; }
FloorplanPoint point(const J& n) { return {n.array_value.at(0).number_value,n.array_value.at(1).number_value}; }
Halo halo(const J& n) { return {n.array_value.at(0).number_value,n.array_value.at(1).number_value,n.array_value.at(2).number_value,n.array_value.at(3).number_value}; }
Box4 box(const J& n) { auto h=halo(n); return {h.w,h.e,h.n,h.s}; }
std::vector<std::string> strings(const J& n) {
    std::vector<std::string> out; for (const auto& s:n.array_value) out.push_back(s.string_value); return out;
}
FloorplanOffsets offsets(const J& n) {
    FloorplanOffsets out; for (const auto& [k,v]:n.object_value) out[k]=point(v); return out;
}
FloorplanRotations rotations(const J& n) {
    FloorplanRotations out; for (const auto& [k,v]:n.object_value) out[k]=v.number_value; return out;
}
std::map<std::string,std::string> stringmap(const J& n) {
    std::map<std::string,std::string> out; for (const auto& [k,v]:n.object_value) out[k]=v.string_value; return out;
}
FloorplanLocalMetrics metrics(const J& n) {
    FloorplanLocalMetrics m;
    for (const auto& v:field(n,"offsets").array_value) m.offsets.emplace_back(v.array_value.at(0).string_value,v.array_value.at(1).number_value,v.array_value.at(2).number_value);
    for (const auto& v:field(n,"pad_union").array_value) m.pad_union.emplace_back(v.array_value.at(0).string_value,v.array_value.at(1).number_value,v.array_value.at(2).number_value,v.array_value.at(3).number_value,v.array_value.at(4).number_value);
    m.zone_wh=point(field(n,"zone_wh")); return m;
}
std::vector<FloorplanTerm> terms(const J& n) {
    std::vector<FloorplanTerm> out;
    for (const auto& v:n.array_value) {
        FloorplanTerm t; t.kind=str(v,"kind"); t.sheet=str(v,"sheet"); t.subject=str(v,"subject"); t.target_raw=str(v,"target_raw");
        if (field(v,"bound").kind!=JsonKind::Null) t.bound=num(v,"bound");
        t.basis=str(v,"basis"); t.enforced=boolean(v,"enforced");
        t.output_roles=strings(field(v,"output_roles")); t.out_refs=strings(field(v,"out_refs")); out.push_back(std::move(t));
    }
    return out;
}
FloorplanZoneShape shape(const J& n) {
    FloorplanZoneShape s; s.w=num(n,"w"); s.h=num(n,"h"); s.top_off=offsets(field(n,"top_off")); s.bot_off=offsets(field(n,"bot_off"));
    s.extra_rot=rotations(field(n,"extra_rot")); s.tag=str(n,"tag"); s.side=str(n,"side"); s.mirror=stringmap(field(n,"mirror")); return s;
}
SomOutline som(const J& n) {
    SomOutline out; out.w=num(n,"w"); out.h=num(n,"h");
    for (const auto& j:field(n,"js").array_value) out.js.push_back({str(j,"ref"),num(j,"pcb_x"),num(j,"pcb_y"),num(j,"rot"),num(j,"x"),num(j,"y"),num(j,"w"),num(j,"h")});
    return out;
}
FloorplanInput input(const J& n) {
    FloorplanInput in;
    for (const auto& s:field(n,"sheets").array_value) in.sheets.push_back(decode_intermediate_circuit_ir(s));
    for (const auto& b:field(n,"bindings").array_value) {
        LinkPortBinding binding; binding.sheet=str(b,"sheet"); binding.net=str(b,"net"); binding.status=str(b,"status"); binding.targets=strings(field(b,"targets"));
        binding.ptype.expect=str(field(b,"ptype"),"expect"); in.link.bindings.push_back(std::move(binding));
    }
    for (const auto& r:field(n,"regulators").array_value) {
        FloorplanRegulator reg; reg.sheet=str(r,"sheet"); reg.ref=str(r,"ref"); reg.value=str(r,"value"); reg.kind=str(r,"kind");
        reg.vin=str(r,"vin"); reg.vout=str(r,"vout"); reg.i_out=num(r,"i_out"); reg.eff=num(r,"eff",1); in.regulators.push_back(std::move(reg));
    }
    if (const auto* si=object_field(n,"si_spec")) in.si_pairs=parse_signal_specs(*si);
    in.som=som(field(n,"som")); in.som_source=str(field(n,"som"),"source");
    if (field(n,"spec").kind!=JsonKind::Null) in.spec=floorplan_spec_from_json(field(n,"spec"),"floorplan.json");
    const auto& pr=field(n,"project"); in.project.name=str(pr,"name");
    const auto off=point(field(pr,"module_offset")); in.project.module_offset={off.first,off.second};
    for (const auto& [k,v]:field(pr,"module_face_anchors").object_value) in.project.module_face_anchors.emplace_back(k,v.string_value);
    in.project.reg_band_prefixes=strings(field(pr,"reg_band_prefixes"));
    in.module_offset=point(field(n,"module_offset"));
    for (const auto& [k,v]:field(n,"sheet_index").object_value) in.sheet_index.emplace_back(k,static_cast<int>(v.number_value));
    auto& g=in.geometry; const auto& z=field(n,"geometry");
    g.zone_box=offsets(field(z,"zone_box")); g.side_of=stringmap(field(z,"side_of")); g.resolvable=stringmap(field(z,"resolvable"));
    g.conn_rot=rotations(field(z,"conn_rot")); g.zone_extra_rot=rotations(field(z,"zone_extra_rot")); g.conn_edge=stringmap(field(z,"conn_edge"));
    for (const auto& [k,v]:field(z,"top_off").object_value) g.top_off[k]=offsets(v);
    for (const auto& [k,v]:field(z,"bot_off").object_value) g.bot_off[k]=offsets(v);
    for (const auto& [k,v]:field(z,"bbox_of").object_value) g.bbox_of[k]=box(v);
    for (const auto& [k,v]:field(z,"refs_by_sheet").object_value) g.refs_by_sheet[k]=strings(v);
    g.mh_refs=strings(field(z,"mh_refs")); g.deferred=strings(field(z,"deferred"));
    for (const auto& [k,v]:field(z,"shapes").object_value) for (const auto& s:v.array_value) g.shapes[k].push_back(shape(s));
    for (const auto& s:strings(field(z,"mirror_refs"))) g.mirror_refs.insert(s);
    for (const auto& [k,v]:field(n,"footprints").object_value) in.footprints[k]={str(v,"source"),sexpr_loads(str(v,"text"))};
    in.footprint_of=stringmap(field(n,"footprint_of")); in.courtyard_dims=offsets(field(n,"courtyard_dims"));
    in.impedance_net_classes=stringmap(field(n,"impedance_net_classes"));
    const auto& co=field(n,"compose"); const auto& index=field(co,"index");
    in.compose.index.hard=terms(field(index,"hard")); in.compose.index.soft=terms(field(index,"soft")); in.compose.index.na=terms(field(index,"na"));
    for (const auto& [k,v]:field(co,"metrics").object_value) in.compose.metrics[k]=metrics(v);
    for (const auto& row:field(co,"shape_metrics").array_value) in.compose.shape_metrics[{str(row,"sheet"),static_cast<int>(num(row,"index"))}]=metrics(field(row,"metrics"));
    for (const auto& v:field(co,"corridors").array_value) in.compose.corridors.emplace_back(v.array_value[0].string_value,
        Box4{v.array_value[1].number_value,v.array_value[2].number_value,v.array_value[3].number_value,v.array_value[4].number_value});
    for (const auto& s:strings(field(co,"wired_participants"))) in.compose.wired_participants.insert(s);
    in.accounting.fallback_events=strings(field(n,"zone_events"));
    if (const auto* counts=object_field(n,"zone_quant")) for (const auto& [k,v]:counts->object_value)
        in.accounting.quantization_engagements[k]=static_cast<std::size_t>(v.number_value);
    return in;
}
FloorplanBlock block(const J& n) {
    FloorplanBlock b; b.name=str(n,"name"); b.kind=str(n,"kind"); b.x=num(n,"x"); b.y=num(n,"y"); b.w=num(n,"w"); b.h=num(n,"h");
    b.edge=str(n,"edge"); b.shape_idx=static_cast<int>(num(n,"shape_idx")); b.side=str(n,"side"); b.zone=str(n,"zone");
    b.n_parts=static_cast<int>(num(n,"n_parts"));b.area=num(n,"area");b.pinned=boolean(n,"pinned");b.layer_pref=str(n,"layer_pref");
    b.reserved=strings(field(n,"reserved"));
    for(const auto& c:field(n,"conns").array_value)b.conns.push_back({c.array_value[0].string_value,c.array_value[1].string_value,c.array_value[2].number_value,c.array_value[3].number_value});
    for(const auto& [k,v]:field(n,"j_aff").object_value)b.j_aff.emplace_back(k,static_cast<int>(v.number_value));
    if(field(n,"order_hint").kind!=JsonKind::Null)b.order_hint=static_cast<int>(num(n,"order_hint"));
    const auto* p=object_field(n,"pull");
    if(p&&p->kind!=JsonKind::Null) {
        FloorplanPull pull;pull.to=str(*p,"to");pull.weight=num(*p,"weight");pull.basis=str(*p,"basis");
        pull.face_present=object_field(*p,"face");pull.exclusive_present=object_field(*p,"exclusive");
        if(pull.face_present)pull.face=str(*p,"face");pull.exclusive=boolean(*p,"exclusive");b.pull=std::move(pull);
    }
    b.fanout_reach=halo(field(n,"fanout_reach")); b.fanout_inset=halo(field(n,"fanout_inset"));
    return b;
}
FloorplanPlan plan(const J& expected) {
    const auto& n=field(expected,"plan"); FloorplanPlan p; p.som=som(field(n,"som")); p.som_source=str(field(n,"som"),"source");
    p.som_x=num(n,"som_x"); p.som_y=num(n,"som_y"); p.board_w=num(expected,"board_w"); p.board_h=num(expected,"board_h");
    p.outline_note=str(expected,"outline_note"); p.punch_free=boolean(n,"punch_free");
    p.factor=num(n,"factor");p.spilled=strings(field(n,"spilled"));p.composition=strings(field(n,"composition"));
    const auto d=point(field(n,"dec_bank")); p.dec_count=static_cast<int>(d.first); p.dec_radius=d.second;
    for (const auto& b:field(n,"edge_blocks").array_value) p.edge_blocks.push_back(block(b));
    for (const auto& b:field(n,"interior_blocks").array_value) p.interior_blocks.push_back(block(b));
    return p;
}
void same(const J& a,const J& b,const std::string& path) {
    require(a.kind==b.kind,path+": type mismatch");
    if (a.kind==JsonKind::Number) require(std::abs(a.number_value-b.number_value)<=1e-8,path+": "+number(a.number_value)+" != "+number(b.number_value));
    else if (a.kind==JsonKind::String) require(a.string_value==b.string_value,path+": string mismatch: "+a.string_value+" != "+b.string_value);
    else if (a.kind==JsonKind::Bool) require(a.bool_value==b.bool_value,path+": bool mismatch");
    else if (a.kind==JsonKind::Array) {
        require(a.array_value.size()==b.array_value.size(),path+": array size mismatch");
        for (std::size_t k=0;k<b.array_value.size();++k) same(a.array_value[k],b.array_value[k],path+"["+std::to_string(k)+"]");
    } else if (a.kind==JsonKind::Object) {
        require(a.object_value.size()==b.object_value.size(),path+": object size mismatch");
        for (const auto& [k,v]:b.object_value) same(field(a,k),v,path+"."+k);
    }
}
void throws(const std::function<void()>& fn,const std::string& fragment) {
    try { fn(); } catch (const std::exception& e) { require(std::string(e.what()).find(fragment)!=std::string::npos,"wrong error: "+std::string(e.what())); return; }
    require(false,"expected error containing "+fragment);
}
void compose_contracts(const std::filesystem::path& dir) {
    const auto fixture=parse_json_file((dir/"compose.json").string());
    FloorplanLegalizeInput base;
    base.board_w=100;base.board_h=100;base.som_core_page={65,65,85,85};
    for(const std::string name:{"a","b"}) base.metrics[name]={{{"p",5,5}},{{"p",0,0,10,10}},{10,10}};
    const std::vector<FloorplanLegalizeVar> initial{{"a",10,10,{5,5},5,5},{"b",10,10,{60,5},60,5}};
    for(const auto& row:fixture.array_value) {
        auto in=base;auto vars=initial;std::vector<std::string> log;
        const auto name=str(row,"name");
        in.board_w=num(row,"width");in.compact=boolean(row,"compact");
        if(boolean(row,"jack"))in.som_j_rects["som_j1"]={40,5,50,15};
        if(boolean(row,"block"))in.fixed_rects.push_back({"obstacle",{0,0,100,100}});
        if(num(row,"demand"))in.channel_demand[{"a","b"}]=static_cast<int>(num(row,"demand"));
        for(const auto& term:field(row,"terms").array_value) {
            FloorplanTerm t;t.kind=term.array_value.at(0).string_value;t.sheet="a";t.subject="a";
            t.target_raw=term.array_value.at(1).string_value;t.enforced=true;t.out_refs={"p"};
            t.basis="independent native migration fixture";
            if(term.array_value.at(2).kind!=JsonKind::Null)t.bound=term.array_value.at(2).number_value;
            in.index.hard.push_back(std::move(t));
        }
        require(floorplan_legalize_compact(in,vars,log)==boolean(row,"ok"),name+": Python feasibility");
        require(log==strings(field(row,"log")),name+": Python decision log");
        std::vector<J> poses;
        for(const auto& v:vars)poses.push_back(jarray({jvalue(v.name),jvalue(v.x),jvalue(v.y)}));
        same(jarray(poses),field(row,"poses"),name+": Python poses/rejection rollback");
        std::reverse(vars.begin(),vars.end());std::reverse(in.index.hard.begin(),in.index.hard.end());
        for(auto& v:vars) {const auto& seed=v.name=="a" ? initial[0]:initial[1];v=seed;}
        std::vector<std::string> second_log;
        require(floorplan_legalize_compact(in,vars,second_log)==boolean(row,"ok"),name+": reordered input feasibility");
        std::reverse(vars.begin(),vars.end());
        for(std::size_t i=0;i<vars.size();++i) {
            require(vars[i].x==field(row,"poses").array_value.at(i).array_value.at(1).number_value&&
                    vars[i].y==field(row,"poses").array_value.at(i).array_value.at(2).number_value,name+": sorted variable order");
        }
    }
    std::vector<std::string> log;auto vars=initial;
    auto changed=base;changed.board_w=std::numeric_limits<double>::quiet_NaN();
    throws([&]{floorplan_legalize_compact(changed,vars,log);},"non-finite");
    changed=base;changed.metrics["a"].offsets.clear();
    throws([&]{floorplan_legalize_compact(changed,vars,log);},"pad union has no offset");
    changed=base;changed.channel_demand[{"a","b"}]=-1;
    throws([&]{floorplan_legalize_compact(changed,vars,log);},"negative channel demand");
    changed=base;changed.index.hard.push_back({"invented","a","a","b",{},"",true,{},{}});
    throws([&]{floorplan_legalize_compact(changed,vars,log);},"unknown term kind");
    changed=base;vars.push_back(vars.front());
    throws([&]{floorplan_legalize_compact(changed,vars,log);},"duplicate movable name");
    vars=initial;changed.fixed_rects.push_back({"a",{0,0,10,10}});
    throws([&]{floorplan_legalize_compact(changed,vars,log);},"both fixed and movable");
    vars=initial;changed=base;vars[0].w=0;
    throws([&]{floorplan_legalize_compact(changed,vars,log);},"nonpositive movable dimensions");
    require(log.empty(),"malformed compose inputs never append acceptance logs");
    require(floorplan_evaluate_terms(base,{}).empty(),"empty term index evaluates without fabricated terms");
}
void mutations() {
    FloorplanInput in; in.som.w=10; in.som.h=8;
    in.footprints["dip"]={"dip",sexpr_loads(R"((footprint "dip" (fp_rect (start -4 -2) (end 4 2) (layer "F.CrtYd") (width 0.05)) (pad "1" thru_hole circle (at -3 0) (size 0.8 0.8)) (pad "2" thru_hole circle (at 3 0) (size 0.8 0.8))))")};
    in.geometry.resolvable["U1"]="dip"; in.geometry.bbox_of["U1"]={-4,-2,4,2};
    Engine e(in); FloorplanZoneShape s; s.w=12;s.h=8;s.top_off["U1"]={5,4};
    const auto pads=e.zone_components(s,true),body=e.zone_components(s,false);
    require(pads.size()==2 && body.size()==1,"pad-only and whole-body punch paths differ");
    require(std::abs(pads[0].dx-1.6)<1e-9 && std::abs(pads[0].w-.8)<1e-9 && pads[0].mask==3,"THT pad exact punch");
    require(body[0].dx==1 && body[0].dy==2 && body[0].w==8 && body[0].h==4 && body[0].mask==3,"conservative body punch");
    s.bot_off=s.top_off;s.top_off.clear();s.side="bottom";
    require(e.zone_components(s,true).front().mask==1,"secondary face is opposite bottom primary");
    auto broken=in; broken.footprints.clear(); throws([&]{Engine bad(broken);},"missing resolved footprint");
    broken=in; broken.som.w=std::numeric_limits<double>::infinity(); throws([&]{Engine bad(broken);},"finite");
    const auto pull=jobject({{"to",jvalue("jack")},{"weight",jvalue(60.0)},{"basis",jvalue("test edge seat")},{"face",jvalue("inboard")},{"exclusive",jvalue(true)}});
    auto spec=jobject({{"edges",jobject({{"N",jarray({jvalue("jack")})}})},
        {"interior",jobject({{"logic",jobject({{"near",jvalue("jack")},{"pull",pull}})}})}});
    require(floorplan_spec_from_json(spec,"fixture.json",std::set<std::string>{"jack","logic"}).interior.at("logic").pull->exclusive,"auditable exclusive pull parses");
    auto duplicate=spec; duplicate.object_value.emplace_back("outline",jobject({{"w",jvalue(0.0)},{"h",jvalue(80.0)}}));
    throws([&]{floorplan_spec_from_json(duplicate,"fixture.json");},"must be > 0");
    const auto missing_anchor=jobject({{"edges",jobject({{"N",jarray({jvalue("jack")})}})},
        {"interior",jobject({{"logic",jobject({{"side",jvalue("E")},{"pull",pull}})}})}});
    throws([&]{floorplan_spec_from_json(missing_anchor,"fixture.json");},"exclusive requires");
    e.plan.board_w=100;e.plan.board_h=100;e.plan.som_x=40;e.plan.som_y=46;
    FloorplanBlock jack; jack.name="jack";jack.edge="N";jack.x=20;jack.y=1.5;jack.w=10;jack.h=8;e.plan.edge_blocks.push_back(jack);
    FloorplanBlock logic;logic.name="logic";logic.zone="@jack";logic.w=6;logic.h=4;
    logic.pull=floorplan_spec_from_json(spec,"fixture.json").interior.at("logic").pull;
    const auto anchor=pack_anchor(e.anchor_row(logic,{}));
    require(anchor.first==25 && anchor.second==11.5,"exclusive inboard pull uses actual connector face");
    auto alias=e.plan;alias.board_w=900;alias.edge_blocks[0].x=-500;
    require(e.plan.board_w==100 && e.plan.edge_blocks[0].x==20,"plan is an independent stage snapshot");
    throws([&]{e.calc("not_registered",jvalue(1),{});},"unregistered calculation");
    throws([&]{e.calc("overmold_side_gap",jvalue(3),{});},"inputs drifted");
    throws([&]{e.fallback("invented_success");},"unregistered fallback");
    broken=in;
    broken.footprints["dip"].document=sexpr_loads(R"((footprint "broken" (fp_rect (start -4 -2) (end 4 2) (layer "F.CrtYd") (width 0.05)) (pad "1" thru_hole circle (size 1 1))))");
    Engine no_pad_at(broken);
    throws([&]{no_pad_at.zone_components(s,true);},"pad kernel found none");
    broken=in;broken.footprints["dip"].source="opaque-provider/Fiducial_1mm.kicad_mod";
    Engine fiducial(broken);const auto fid_halo=fiducial.fanout(s,true);
    require(fid_halo.first.w==0&&fid_halo.first.e==0&&fid_halo.second.w==0&&fid_halo.second.e==0,
            "fiducial exclusion follows source identity, not an opaque footprint pool key");
}
// Vectors below were executed against the original Python orchestration on
// 2026-09-18, not inferred from native output. Widths straddle the hand-derived
// edge floor: 2 mm reach + 80 mm bodies + .3 gap + 20 margins - .1 tolerance.
void pack_behavior() {
    FloorplanInput in;in.som.w=50;in.som.h=42;
    for(double width:{101.2,103.2}) {
        Engine e(in);e.board_size(width,120);
        FloorplanBlock a,b;a.name="a";b.name="b";a.kind=b.kind="edge";a.edge=b.edge="S";
        a.fanout_reach={2,0,0,0};e.plan.edge_blocks={a,b};
        e.zbox={{"a",{40,10}},{"b",{40,10}}};e.edge_of={{"a","S"},{"b","S"}};e.max_reach=2;
        require(e.attempt_pack(false)==(width>102.2),"complete pack enforces edge-run width floor");
        const auto& first=e.plan.edge_blocks[0];const auto& second=e.plan.edge_blocks[1];
        require(first.edge=="S"&&second.edge=="S","width rejection does not silently change edge membership");
        require(first.x==12&&first.y==108.5&&std::abs(second.x-52.3)<1e-12&&second.y==108.5,"frozen edge-run poses");
    }
    in.som.w=20;in.som.h=20;
    for(const std::string connected:{"small","large"}) {
        Engine e(in);e.board_size(100,80);
        FloorplanBlock a,b;a.name="large";b.name="small";a.kind=b.kind="interior";a.zone=b.zone="E";
        e.plan.interior_blocks={a,b};e.zbox={{"large",{30,20}},{"small",{10,20}}};
        e.affinity[connected]={{"unplaced",10}};
        require(e.attempt_pack(false),"connectivity-order fixture fits");
        const auto& large=e.plan.interior_blocks[0];const auto& small=e.plan.interior_blocks[1];
        const bool small_first=connected=="small";
        require(large.x==(small_first?59:65)&&large.y==(small_first?8:30)&&small.x==75&&small.y==(small_first?30:9),
                "connectivity precedes area in actual seating and refinement");
        require(e.plan.accounting.fallback_events.empty(),"direct seating incurs no retry fallback");
    }
    // Same declared layout inputs, independent fresh engines. Equal estimates
    // must retain the conservative incumbent, and prior accounting survives.
    CircuitSheetIr logic;logic.name="logic";
    logic.parts.push_back({"R1","Device:R","10k","Resistor_SMD:R_0603_1608Metric",{},{},{}});
    in.sheets={logic};in.geometry.zone_box["logic"]={12,8};
    FloorplanSpec fixed;fixed.outline={{100,80}};in.spec=fixed;
    in.accounting.fallback_events={"prior_zone_event"};
    const auto first=build_floorplan(in),second=build_floorplan(in);
    require(!first.punch_free,"equal fixed-plan estimate retains conservative proof");
    require(first.accounting.fallback_events==std::vector<std::string>{"prior_zone_event","punch_free_plan_rejected"},
            "rejected free trial restores incumbent accounting, preserving prior events once");
    same(floorplan_plan_json(first),floorplan_plan_json(second),"repeat independent fixed build");
    require(first.board_w==100&&first.board_h==80&&first.som_x==40&&first.som_y==30,"fixed board and module pose");
    auto changed=in;changed.module_offset={{2,-3}};
    const auto moved=build_floorplan(changed);
    require(moved.som_x==42&&moved.som_y==27&&first.som_x==40&&first.som_y==30,"new offset rebuild cannot mutate saved stage");
    changed=in;changed.spec->outline={{20,20}};
    throws([&]{build_floorplan(changed);},"do not fit the fixed outline");
    changed=in;changed.spec->outline={{std::numeric_limits<double>::quiet_NaN(),80}};
    throws([&]{build_floorplan(changed);},"finite");
    const auto captured=generate_floorplan(in);
    auto downstream=captured.plan;downstream.board_w=900;downstream.interior_blocks[0].x=-500;
    downstream.composition.push_back("downstream placement");
    require(captured.plan.board_w==100&&captured.plan.interior_blocks[0].x!=-500&&captured.plan.composition.empty(),
            "PCB placement cannot mutate captured floorplan stage");
    const auto rerendered=render_floorplan_documents(captured.plan,in);
    require(rerendered.svg==captured.documents.svg&&rerendered.markdown==captured.documents.markdown,
            "stage rerender is byte stable without solver or global context restoration");
    auto unicode=captured.plan;unicode.som_source="<&>";auto& label=unicode.interior_blocks[0];
    label.name.clear();for(int k=0;k<20;++k)label.name+="μ";label.w=20;
    const auto svg=render_floorplan_svg(unicode,{});
    require(svg.find("font-size=\"9.2\"")!=std::string::npos&&svg.find("&lt;&amp;&gt;")!=std::string::npos,
            "SVG text fits Unicode code points and escapes XML metacharacters");
    unicode.board_w=std::numeric_limits<double>::infinity();
    throws([&]{render_floorplan_svg(unicode,{});},"board dimensions");
    const auto seed=render_floorplan_spec_json(unicode);
    require(seed.find("\\u03bc")!=std::string::npos,"seed JSON escapes Unicode as Python does");
    unicode.interior_blocks[0].name="\xf0\x9f\x94\xa7\n\"\\";
    require(render_floorplan_spec_json(unicode).find("\\ud83d\\udd27\\n\\\"\\\\")!=std::string::npos,
            "seed JSON emits surrogate pairs and control/quote escapes");
    unicode.interior_blocks[0].name=std::string(1,static_cast<char>(0xc0));
    throws([&]{render_floorplan_spec_json(unicode);},"invalid UTF-8");
    changed=in;changed.spec->outline.reset();
    const auto automatic=build_floorplan(changed);
    require(automatic.board_w==50&&automatic.board_h==30&&automatic.som_x==15&&automatic.som_y==5,
            "frozen synthetic automatic search winner");
    require(automatic.interior_blocks[0].x==37&&automatic.interior_blocks[0].y==11,"automatic final compact repack pose");
    int passes=0;
    for(const auto& d:automatic.accounting.decisions)if(d.name=="outline_candidates") {
        const auto counts=jobject(d.inputs);++passes;
        for(const auto& [key,value]:std::map<std::string,int>{{"generated",1686},{"reject_aspect",820},
                {"reject_min_area",0},{"reject_not_smaller",519},{"reject_pack",292},{"reject_law5_budget",0},{"accepted",55}})
            require(num(counts,key)==value,"frozen synthetic search tally "+key);
    }
    require(passes==2&&!automatic.punch_free,"both reservation policies execute; tied free pass rejected");
    const std::map<std::string,std::size_t> quanta{{"outline_fine_grid",164},{"outline_grow_step",10},
        {"outline_snap_up",20},{"run_overflow_tol",696},{"som_pose_half_mm",1394},{"quant_credit",696}};
    require(automatic.accounting.quantization_engagements==quanta,"all synthetic search quantization engagements accounted exactly");
}
void cross_behavior() {
    FloorplanInput in;in.som.w=20;in.som.h=20;
    in.footprints["one"]={"synthetic-one-pad",sexpr_loads(R"((footprint "one" (fp_rect (start -1 -1) (end 1 1) (layer "F.CrtYd") (width 0.05)) (pad "1" smd rect (at 0 0) (size 1 1))))")};
    in.footprint_of["Test:One"]="one";
    for(int k=1;k<=2;++k) {
        const std::string name=k==1?"source":"sink",ref="U"+std::to_string(k*1000+1);
        CircuitSheetIr s;s.name=name;s.parts.push_back({"U1","Test:One","one","Test:One",{},{},{}});
        s.nets.push_back({"signal","port",{{"U1","1"}}});in.sheets.push_back(s);in.sheet_index.emplace_back(name,k);
        in.geometry.zone_box[name]={2,2};in.geometry.top_off[name][ref]={0,0};in.geometry.side_of[ref]="top";
        in.geometry.resolvable[ref]="one";in.geometry.bbox_of[ref]={-1,-1,1,1};
    }
    FloorplanZoneShape top;top.w=top.h=2;top.top_off["U2001"]={0,0};
    auto bottom=top;bottom.side="bottom";in.geometry.shapes["sink"]={top,bottom};
    for(bool impedance:{false,true}) {
        if(impedance)in.impedance_net_classes["signal"]="DP100_TMDS";
        Engine e(in);e.prepare_cross();
        FloorplanBlock a,b;a.name="source";b.name="sink";a.w=a.h=b.w=b.h=2;b.x=3;b.y=4;
        e.plan.interior_blocks={a,b};
        require(e.estimate()==5,"hand-computed 3-4-5 cross-subsystem MST");
        e.plan.interior_blocks[1].shape_idx=1;e.plan.interior_blocks[1].side="bottom";
        require(std::abs(e.estimate()-(impedance?12.6:7.2))<1e-12,"actual selected-bottom topology charges correct via class");
        const std::vector<const FloorplanBlock*> partial{&e.plan.interior_blocks[1]};
        require(e.estimate(partial,"sink")==0,"one-sheet partial estimator excludes absent endpoint");
        require(e.n_impedance==(impedance?1:0),"impedance split reflects source class, not sheet name");
    }
    // Change the source document, not the already-captured expected points.
    auto changed=in;
    changed.footprints["one"].document=sexpr_loads(R"((footprint "one" (fp_rect (start -1 -1) (end 1 1) (layer "F.CrtYd") (width 0.05)) (pad "missing" smd rect (at 0 0) (size 1 1))))");
    Engine missing(changed);missing.prepare_cross();
    require(missing.cross_nets.empty(),"source-pad mutation changes estimator membership; no stale path cache");
    changed=in;changed.geometry.top_off["sink"]["U2001"].first=std::numeric_limits<double>::infinity();
    throws([&]{Engine bad(changed);},"non-finite geometry");
    changed=in;changed.geometry.bbox_of["U2001"]={1,-1,-1,1};
    throws([&]{Engine bad(changed);},"inverted courtyard");
}
void frozen(const std::filesystem::path& dir,const std::string& name,bool geometry_only) {
    const auto fixture=parse_json_file((dir/(name+".json")).string());
    const auto in=input(field(fixture,"input"));
    const auto expected=board_policy_reference::migrate(field(fixture,"expected"),dir.parent_path());
    // Exercise native registry and formatting independently of the solver:
    // the values/order here come from the frozen Python decision stream.
    Engine replay(in);replay.ledger_open();std::size_t calculation=0;
    for(const auto& row:field(expected,"ledger").array_value) {
        if(str(row,"kind")=="STEP"&&str(row,"name")=="sizing.pass")
            replay.ledger_pass(str(row,"text").find("punch=free")!=std::string::npos);
        if(str(row,"kind")=="CALC") {
            const auto& d=field(expected,"decisions").array_value.at(calculation++);
            replay.calc(str(d,"name"),field(d,"value"),field(d,"inputs").object_value,str(d,"step"));
        }
    }
    std::string replay_expected;
    for(const auto& row:field(expected,"ledger").array_value)replay_expected+=str(row,"text")+"\n";
    require(render_floorplan_ledger(replay.plan)==replay_expected,name+": frozen decision ledger replay");
    Engine e(in);e.initialize();e.prepare_geometry();e.prepare_cross();
    const auto geometry=parse_json_file((dir/(name+"_geometry.json")).string());
    for(const auto& row:geometry.array_value) {
        const auto sheet=str(row,"sheet");const int k=static_cast<int>(num(row,"index"));
        Halo reach,inset;
        if(k)std::tie(reach,inset)=e.fanout(in.geometry.shapes.at(sheet).at(k),false);
        else for(const auto* b:e.blocks())if(b->name==sheet){reach=b->fanout_reach;inset=b->fanout_inset;}
        const auto path=name+".prepared."+sheet+"["+std::to_string(k)+"]";
        same(halo_json(reach),field(row,"reach"),path+".reach");
        same(halo_json(inset),field(row,"inset"),path+".inset");
        for(int policy:{0,1}) {
            std::vector<J> comps;
            for(const auto& c:e.components[policy].at({sheet,k}))
                comps.push_back(jarray({jvalue(c.dx),jvalue(c.dy),jvalue(c.w),jvalue(c.h),jvalue(c.mask)}));
            same(jarray(comps),field(row,policy?"free_components":"conservative_components"),path+".components");
        }
    }
    e.plan=plan(expected);
    same(export_floorplan_spec(e.plan),parse_json_file((dir/(name+"_export.json")).string()),name+".export");
    require(std::abs(e.estimate()-num(expected,"cross_estimate"))<1e-8,name+": frozen placed-board cross estimate");
    const auto notes=build_floorplan_notes(e.plan,in);
    std::vector<J> note_rows;
    for(const auto& n:notes)note_rows.push_back(jobject({{"n",jvalue(n.n)},{"block",jvalue(n.block)},{"short",jvalue(n.short_text)},{"long",jvalue(n.long_text)}}));
    same(jarray(note_rows),field(expected,"notes"),name+".notes");
    std::ifstream svgfile(dir/(name+".svg"));const std::string svg((std::istreambuf_iterator<char>(svgfile)),{});
    const auto rendered=render_floorplan_svg(e.plan,notes);
    if(rendered!=svg) {
        std::size_t k=0;while(k<std::min(rendered.size(),svg.size())&&rendered[k]==svg[k])++k;
        throw std::runtime_error(name+": SVG bytes at "+std::to_string(k)+": "+rendered.substr(k,100)+" expected "+svg.substr(k,100));
    }
    require(true,name+": byte exact SVG");
    std::ifstream mdfile(dir/(name+".md"));const std::string md((std::istreambuf_iterator<char>(mdfile)),{});
    const auto markdown=render_floorplan_md(e.plan,notes,in);
    if(markdown!=md) {
        std::size_t k=0;while(k<std::min(markdown.size(),md.size())&&markdown[k]==md[k])++k;
        throw std::runtime_error(name+": Markdown bytes at "+std::to_string(k)+": "+markdown.substr(k,100)+" expected "+md.substr(k,100));
    }
    require(true,name+": byte exact Markdown");
    if(!in.si_pairs.empty()) {
        auto missing_si=in;missing_si.si_pairs.clear();
        throws([&]{render_floorplan_md(e.plan,notes,missing_si);},"has no row");
    }
    if (geometry_only) return;
    auto result=build_floorplan(in);auto out=floorplan_plan_json(result);
    for (const auto& [key,value]:field(expected,"plan").object_value) same(field(out,key),value,name+".plan."+key);
    same(field(out,"board_w"),field(expected,"board_w"),name+".board_w");
    same(field(out,"board_h"),field(expected,"board_h"),name+".board_h");
    same(field(out,"outline_note"),field(expected,"outline_note"),name+".outline_note");
    const auto& account=field(out,"accounting");same(field(account,"fallback_events"),field(expected,"events"),name+".fallback_events");
    auto expected_quant=jobject({});
    for(const auto& [key,v]:field(expected,"quantization").object_value)
        if(v.number_value!=0)expected_quant.object_value.emplace_back(key,v);
    // The original capture missed native legalizer/spatial/fanout calls because
    // its Python census never observed those kernels. A separate function-entry
    // observer ran the committed, pre-instrumentation kernel (not these counters).
    const auto native_counts=parse_json_file((dir.parent_path()/"verification_audits/native_producer_counts.json").string());
    for(const auto& [key,v]:field(field(native_counts,"counts"),name).object_value) {
        require(v.number_value>0,name+": independently observed native instrumentation gap");
        auto found=std::find_if(expected_quant.object_value.begin(),expected_quant.object_value.end(),
            [wanted=key](const auto& item){return item.first==wanted;});
        if(found==expected_quant.object_value.end())expected_quant.object_value.emplace_back(key,v);
        else found->second.number_value+=v.number_value;
    }
    same(field(account,"quantization_engagements"),expected_quant,name+".quantization_engagements");
    std::vector<J> calculations;
    std::string ledger;
    for (const auto& d:result.accounting.decisions) {
        if (d.kind=="CALC") calculations.push_back(jobject({{"name",jvalue(d.name)},{"value",d.value},{"inputs",jobject(d.inputs)},{"step",jvalue(d.step)}}));
        ledger+=d.text+"\n";
    }
    same(jarray(calculations),field(expected,"decisions"),name+".decisions");
    std::string expected_ledger;
    for (const auto& d:field(expected,"ledger").array_value) expected_ledger+=str(d,"text")+"\n";
    require(ledger==expected_ledger,name+": decision ledger exact text");
    const auto documents=render_floorplan_documents(result,in);
    require(documents.svg==svg,name+": solved plan SVG exact bytes");
    require(documents.markdown==md,name+": solved plan Markdown exact bytes");
    require(render_floorplan_ledger(result)==expected_ledger,name+": public ledger exact bytes");
    same(export_floorplan_spec(result),parse_json_file((dir/(name+"_export.json")).string()),name+": solved seed");
    const auto seed=read_bytes(dir/(name+"_seed.json"));
    require(render_floorplan_spec_json(result)==seed,name+": solved seed exact Python bytes");
    TemporaryOutput publication;
    const auto paths=write_floorplan_documents(documents,publication.directory);
    require(paths==std::vector<std::filesystem::path>{publication.directory/"FLOORPLAN.svg",publication.directory/"FLOORPLAN.md"},
            name+": explicit published paths");
    require(read_bytes(paths[0])==svg&&read_bytes(paths[1])==md,name+": published reports exact bytes");
    const auto seed_path=publication.directory/"floorplan.json";
    require(write_floorplan_spec(result,seed_path)==seed_path&&read_bytes(seed_path)==seed,name+": published seed exact bytes");
    require(load_floorplan_spec(seed_path.string())->names().size()==result.edge_blocks.size()+result.interior_blocks.size(),
            name+": exported spec reloads every subsystem");
    const FloorplanDocuments replacement{{},"replacement SVG\n","replacement Markdown\n"};
    write_floorplan_documents(replacement,publication.directory);
    require(read_bytes(paths[0])==replacement.svg&&read_bytes(paths[1])==replacement.markdown,name+": replaces existing documents");
    throws([&]{write_floorplan_documents(documents,paths[0]);},"filesystem");
    require(!load_floorplan_spec((publication.directory/"missing.json").string()),name+": missing optional spec");
}
}  // namespace
int main(int argc,char** argv) {
    try {
        const std::filesystem::path dir=argc>1 ? argv[1]:"native/tests/data/floorplan";
        const bool geometry_only=argc>2 && std::string(argv[2])=="--geometry-only";
        compose_contracts(dir);mutations();pack_behavior();cross_behavior();frozen(dir,"devkit_mini",geometry_only);frozen(dir,"carrier",geometry_only);
        std::cout<<"floorplan contracts: "<<checks<<" checks passed"<<(geometry_only ? " (geometry/estimator slice)":"")<<"\n";
        return 0;
    } catch (const std::exception& e) { std::cerr<<"floorplan contracts: "<<e.what()<<"\n";return 1; }
}
