// Frozen primitive/formatter operands plus current solver requirements.
// No Python, installed footprint library, live board output, or source inspection.
#include "../src/floorplan_internal.hpp"
#include "board_policy_ledger_reference.hpp"
#include "floorplan_precision_fixture.hpp"
#include "experiment_metric_contracts.hpp"
#include "../src/near_translation_domain_internal.hpp"

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
void facing_projection_contracts() {
    for(const auto [dx,dy]:std::vector<FloorplanPoint>{{1,0},{-1,0},{0,1},{0,-1},{1,1},{-1,1},{1,-1},{-1,-1}})
        for(bool source_moves:{false,true})for(bool compact:{false,true})for(bool both_back:{false,true})for(int target_kind:{0,1,2}) {
            if(both_back&&(dx==0||dy==0))continue;
            if(target_kind&&!source_moves)continue;
            FloorplanLegalizeInput in;in.board_w=in.board_h=60;in.compact=compact;
            const FloorplanPoint s{30,30},t{30-10*dx,30+(dx!=0&&dy!=0&&!both_back?5:-10)*dy};
            const std::string target=target_kind==1?"@som":target_kind==2?"som_j1":"target";
            in.metrics["source"].offsets={{"out",1+dx,1+dy},{"in",1-dx,1-dy}};
            in.metrics[target].offsets={{"p",1,1}};
            if(target_kind==1)in.som_core_page={t.first+in.origin.first,t.second+in.origin.second,t.first+2+in.origin.first,t.second+2+in.origin.second};
            if(target_kind==2)in.som_j_rects[target]={t.first,t.second,t.first+2,t.second+2};
            const std::string fixed=source_moves?target:"source",moving=source_moves?"source":target;
            const auto fp=source_moves?t:s,mp=source_moves?s:t;
            in.fixed_poses[fixed]=fp;in.fixed_rects={{fixed,{fp.first,fp.second,fp.first+2,fp.second+2}}};
            FloorplanTerm term;term.kind="facing";term.subject="source";term.target_raw=target;
            term.enforced=true;term.require_positive_facing=true;term.out_refs={"out"};in.index.hard={term};
            std::vector<FloorplanLegalizeVar> vars{{moving,2,2,mp,mp.first,mp.second}};
            std::vector<std::string> log;int retries=0;in.facing_retry_started=[&]{++retries;};
            QuantizationCounts counts;
            const bool accepted=floorplan_legalize_compact_accounted(in,vars,log,counts);
            require(counts.at("legalize_bound_precision4dp")>0&&counts.at("legalize_centroid_precision4dp")>0,
                "facing retry lost executed projection or centroid work");
            if(!accepted) {
                // A separable restriction cannot promise every feasible
                // half-plane solution. Failed retries must not publish poses.
                require(both_back,"strict facing retry must rescue backward group "+std::to_string(dx)+","+std::to_string(dy)+" source_moves="+std::to_string(source_moves));
                require(retries==1&&vars[0].x==mp.first&&vars[0].y==mp.second,"failed facing retry changed caller poses or lost accounting");
                continue;
            }
            require(retries==1,"strict facing retry must be counted once");
            auto poses=in.fixed_poses;poses[moving]={vars[0].x,vars[0].y};
            require(floorplan_evaluate_terms(in,poses).front().ok,"projected cuts bypassed exact facing gate");
            const auto seed=vars;log.clear();retries=0;
            require(floorplan_legalize_compact(in,vars,log)&&retries==0,"valid facing incumbent must skip retry");
            require(vars[0].x==seed[0].x&&vars[0].y==seed[0].y,"valid facing incumbent moved");
        }
}
void primary_fanout_contracts() {
    // Two 20 mm groups cannot be separated as rectangles on this board, but
    // sparse reservations on their opposite faces interlock with 1 mm gaps.
    for(int direction=0;direction<4;++direction)for(bool compact:{false,true}) {
        FloorplanLegalizeInput in;in.board_w=25;in.board_h=25;in.compact=compact;
        FloorplanPoint a{.5,.5},b{4.5,.5};
        Comp ca{0,0,3,20,2},cb{17,0,3,20,1};
        if(direction%2){a.first=4.5;b.first=.5;ca.dx=17;cb.dx=0;}
        if(direction>=2){std::swap(a.first,a.second);std::swap(b.first,b.second);
            std::swap(ca.dx,ca.dy);std::swap(ca.w,ca.h);std::swap(cb.dx,cb.dy);std::swap(cb.w,cb.h);}
        in.fixed_rects={{"a",{a.first,a.second,a.first+20,a.second+20}}};in.fixed_poses["a"]=a;
        for(const auto* name:{"a","b"})in.metrics[name]={{{"p",10,10}},{{"p",0,0,20,20}},{20,20}};
        in.index.hard.push_back({"near_max","b","b","a",100,"interlocking reservations",true,{},{}});
        in.primary_fanout["a"]={{},{},1,3};in.primary_fanout["b"]={{},{},2,3};
        std::vector<FloorplanLegalizeVar> vars{{"b",20,20,b,b.first,b.second}};
        const auto seed=vars;std::vector<std::string> log;
        require(!floorplan_legalize_compact(in,vars,log),"whole rectangles must reject the interlocking witness");
        in.primary_fanout["a"].children=std::vector<Comp>{ca};
        in.primary_fanout["b"].children=std::vector<Comp>{cb};
        int retries=0;in.reservation_retry_started=[&]{++retries;};vars=seed;log.clear();
        QuantizationCounts counts;
        const bool accepted=floorplan_legalize_compact_accounted(in,vars,log,counts);
        if(!accepted)for(const auto& line:log)std::cerr<<line<<'\n';
        require(accepted&&retries==1,"one bounded reservation retry must recover the interlocking layout");
        require(counts.at("occupancy_component_precision4dp")>0,"exact final child geometry must be accounted");
        Occupancy physical(25,25,.3,2,1,1,.05);
        physical.add(a.first,a.second,20,20,{},{},1,{ca});
        require(physical.fits_exhaustive(vars[0].x,vars[0].y,20,20,{},{},2,{cb}),
            "independent exhaustive occupancy rejects child geometry finalist");
        auto blocked=in;blocked.primary_fanout["a"].children=std::vector<Comp>{{0,0,20,20,2}};
        vars=seed;log.clear();retries=0;
        require(!floorplan_legalize_compact(blocked,vars,log)&&retries==1,
            "full secondary-face obstacle must reject after one recorded retry");
        require(vars[0].x==seed[0].x&&vars[0].y==seed[0].y,"failed physical retry mutated caller pose");
        auto roomy=in;roomy.board_w=80;roomy.board_h=80;vars={{"b",20,20,{40,40},40,40}};
        log.clear();retries=0;
        require(floorplan_legalize_compact(roomy,vars,log)&&retries==0,
            "accepted conservative incumbent must not execute physical retry");
        auto invalid=in;invalid.primary_fanout["a"].occupied_mask=1;
        throws([&]{auto trial=seed;std::vector<std::string> messages;floorplan_legalize_compact(invalid,trial,messages);},
            "child reservation face census mismatch");
    }
    for(bool compact:{false,true})for(int face:{1,2}) {
        FloorplanLegalizeInput in;in.board_w=60;in.board_h=60;in.compact=compact;
        for(const auto* name:{"a","b"})
            in.metrics[name]={{{"p",5,5}},{{"p",0,0,10,10}},{10,10}};
        in.index.hard.push_back({"near_max","a","a","b",100,"opposite-face witness",true,{},{}});
        in.primary_fanout["a"]={{},{},face,face};
        in.primary_fanout["b"]={{},{},3-face,3-face};
        std::vector<FloorplanLegalizeVar> vars{{"a",10,10,{20,20},20,20},{"b",10,10,{20,20},20,20}};
        const auto seed=vars;std::vector<std::string> log;
        require(floorplan_legalize_compact(in,vars,log),"two movable disjoint-face bodies may overlap");
        require(vars[0].x==vars[1].x&&vars[0].y==vars[1].y,"legalizer separated disjoint movable bodies");
        Occupancy physical(60,60,.3,2,1,1,.05);
        const auto physical_anchor=vars[0];
        physical.add(vars[0].x,vars[0].y,10,10,{},{},face,{});
        require(physical.fits_exhaustive(vars[1].x,vars[1].y,10,10,{},{},3-face,{}),
            "independent occupancy disagrees with opposite-face overlap");
        const std::vector<Comp> tht{{4,4,2,2,3}};
        require(!physical.fits_exhaustive(vars[1].x,vars[1].y,10,10,{},{},3-face,tht),
            "independent occupancy must reject overlapping through-hole reservation");
        in.primary_fanout["b"].occupied_mask=3;vars=seed;log.clear();
        require(floorplan_legalize_compact(in,vars,log),"mixed-face witness must retain feasible separated placement");
        require(physical.fits_exhaustive(vars[1].x-vars[0].x+physical_anchor.x,vars[1].y-vars[0].y+physical_anchor.y,
            10,10,{},{},3-face,tht),"mixed-face legalization retained a physical collision");
    }
    for(int direction=0;direction<4;++direction) {
        // Body and pad hull favour different proximity axes. The legal body
        // fits a narrow slot; its pad already satisfies the jack constraint.
        FloorplanLegalizeInput in;
        in.board_w=60;in.board_h=60;in.compact=true;in.clear=.25;
        in.metrics["v"]={{{"p",18.5,1.5}},{{"p",18,1,19,2}},{20,20}};
        in.som_j_rects["som_j1"]={38,30,39,31};
        if(direction>=2) {
            in.metrics["v"]={{{"p",18.5,18.5}},{{"p",18,18,19,19}},{20,20}};
            in.som_j_rects["som_j1"]={38,29,39,30};
        }
        if(direction%2) {
            auto& [ref,x,y]=in.metrics["v"].offsets[0];(void)ref;std::swap(x,y);
            auto& [pad,x0,y0,x1,y1]=in.metrics["v"].pad_union[0];(void)pad;
            std::swap(x0,y0);std::swap(x1,y1);
            auto& jack=in.som_j_rects["som_j1"];
            std::swap(jack.x0,jack.y0);std::swap(jack.x1,jack.y1);
        }
        in.index.hard.push_back({"near_max","v","v","som_j1",13,"pad-axis witness (includes 4 mm solver guard)",true,{},{}});
        in.fixed_rects={{"west",{0,0,19.75,60}},{"east",{40.25,0,60,60}},
                        {"north",{0,0,60,19.75}},{"south",{0,40.25,60,60}}};
        std::vector<FloorplanLegalizeVar> vars{{"v",20,20,{20,20},20,20}};
        std::vector<std::string> log;
        const bool ok=floorplan_legalize_compact(in,vars,log);
        if(!ok)for(const auto& line:log)std::cerr<<line<<'\n';
        require(ok,"pad-hull axis preserves feasible narrow slot");
        require(std::count(log.begin(),log.end(),"retry: near constraints use selected pad-hull axes")==1,
            "bounded pad-hull retry must be reported exactly once");
        require(vars[0].x==20&&vars[0].y==20,"pad-hull witness changed pinned pose");
        const auto terms=floorplan_evaluate_terms(in,{{"v",{20,20}}});
        require(terms.size()==1&&terms[0].ok&&terms[0].measured==8,"independent pad gap is eight mm");
        auto repeat=vars;std::vector<std::string> repeated_log;
        require(floorplan_legalize_compact(in,repeat,repeated_log)&&repeat[0].x==20&&repeat[0].y==20&&
            repeated_log==log,"pad-hull decision must repeat deterministically");
    }
    // Independent rectangular witnesses: each active face needs reach 2 minus
    // the other body's 0.5 inset, not the nominal 0.3 clearance. Pull from all
    // four directions so both endpoint orders and both axes are exercised.
    for (int direction=0;direction<4;++direction) {
        FloorplanLegalizeInput in;
        in.board_w=60;in.board_h=60;in.compact=true;
        in.fixed_rects={{"anchor",{20,20,30,30}}};
        in.fixed_poses["anchor"]={20,20};
        in.metrics["v"]={{{"p",5,5}},{{"p",0,0,10,10}},{10,10}};
        in.metrics["anchor"]=in.metrics.at("v");
        in.index.hard.push_back({"flow_hop","v","v","anchor",100,"fanout witness",true,{},{}});
        const std::array<FloorplanPoint,4> seeds{{{40,20},{0.5,20},{20,40},{20,0.5}}};
        const auto seed=seeds.at(direction);
        const std::vector<FloorplanLegalizeVar> initial{{"v",10,10,seed,seed.first,seed.second}};
        Halo reach;
        if(direction==0)reach.w=2;
        if(direction==1)reach.e=2;
        if(direction==2)reach.n=2;
        if(direction==3)reach.s=2;
        in.primary_fanout["v"]={reach,{},1};
        in.primary_fanout["anchor"]={{},{.5,.5,.5,.5},1};
        const auto run=[&](const FloorplanLegalizeInput& input) {
            auto vars=initial;std::vector<std::string> log;
            require(floorplan_legalize_compact(input,vars,log),"fanout witness must compact legally");
            const auto& v=vars.front();
            return direction==0?v.x-30:direction==1?20-v.x-v.w:
                   direction==2?v.y-30:20-v.y-v.h;
        };
        require(std::abs(run(in)-1.5)<1e-9,"directional reach minus opposite inset");
        auto opposite=in;opposite.primary_fanout["anchor"].mask=2;
        require(std::abs(run(opposite)-.3)<1e-9,"opposite-face primary fanout is inactive");
        auto disjoint=opposite;
        disjoint.primary_fanout["v"].occupied_mask=1;
        disjoint.primary_fanout["anchor"].occupied_mask=2;
        require(run(disjoint)<0,"proven disjoint faces may share XY space");
        auto unknown=disjoint;unknown.primary_fanout["v"].occupied_mask=0;
        require(std::abs(run(unknown)-.3)<1e-9,"one unknown occupied-face mask cannot certify disjointness");
        auto mixed=disjoint;mixed.primary_fanout["v"].occupied_mask=3;
        require(std::abs(run(mixed)-.3)<1e-9,"opposite-face children retain conservative separation");
        mixed=disjoint;mixed.primary_fanout["anchor"].occupied_mask=3;
        require(std::abs(run(mixed)-.3)<1e-9,"fixed THT/secondary reservations must not disappear");
        auto channel_faces=disjoint;channel_faces.channel_demand[{"v","anchor"}]=6;
        require(std::abs(run(channel_faces)-3.2)<1e-9,"disjoint faces retain wider wiring-channel requirement");
        auto malformed=disjoint;malformed.primary_fanout["v"].occupied_mask=2;
        throws([&]{run(malformed);},"invalid complete occupancy mask");
        malformed=disjoint;malformed.primary_fanout["v"].occupied_mask=4;
        throws([&]{run(malformed);},"invalid complete occupancy mask");
        malformed=disjoint;malformed.primary_fanout["anchor"].mask=0;
        throws([&]{run(malformed);},"invalid complete occupancy mask");
        auto logical=in;logical.primary_fanout["anchor"].mask=0;
        require(std::abs(run(logical)-.3)<1e-9,"logical exclusions retain nominal clearance");
        auto primitive=in;primitive.primary_fanout.clear();
        require(std::abs(run(primitive)-.3)<1e-9,"empty fanout map keeps primitive API");
        auto outset=in;outset.primary_fanout["anchor"].inset={-.5,-.5,-.5,-.5};
        require(std::abs(run(outset)-2.5)<1e-9,"negative inset expands required separation");
        auto channel=in;channel.clear=3;
        require(std::abs(run(channel)-3)<1e-9,"fanout never weakens nominal clearance");
        channel=in;channel.channel_demand[{"v","anchor"}]=6;
        require(std::abs(run(channel)-3.2)<1e-9,"fanout never weakens wiring-channel demand");
        auto punch=in;punch.primary_fanout["v"].mask=2;punch.primary_fanout["anchor"].mask=3;
        require(std::abs(run(punch)-1.5)<1e-9,"two-face punch remains active against bottom body");
        auto bad=in;bad.primary_fanout.erase("v");
        throws([&]{run(bad);},"missing movable primary fanout");
        bad=in;bad.primary_fanout.erase("anchor");
        throws([&]{run(bad);},"missing fixed primary fanout");
        bad=in;bad.primary_fanout["unknown"]={};
        throws([&]{run(bad);},"unknown primary fanout");
        bad=in;bad.primary_fanout["v"].mask=4;
        throws([&]{run(bad);},"invalid primary fanout");
        bad=in;bad.primary_fanout["v"].reach.w=std::numeric_limits<double>::infinity();
        throws([&]{run(bad);},"non-finite");
    }
    // Impossible Y separation must flip to X and carry X's actual requirement.
    // Reusing 0.3 after this flip was the live UART/mechanical failure mode.
    const std::vector<std::pair<std::string,Box4>> fixed{{"anchor",{0,0,10,6}}};
    const auto repaired=legalize_repair_axis(false,{"v"},{5},10,.3,
        {{false,"#anchor","v",.3,true,1.7501}},fixed,{},2);
    require(repaired.ok&&repaired.flips.size()==1,"Y infeasibility repairs by one flip");
    require(repaired.seps.size()==1&&repaired.seps[0].axis_x&&!repaired.seps[0].flippable,
        "repair preserves one nonflippable separation");
    require(repaired.seps[0].gap==1.7501&&repaired.seps[0].flipped_gap==.3,
        "axis flip transports its directional gap");
    const auto x=legalize_repair_axis(true,{"v"},{5},30,.3,repaired.seps,fixed,{},2);
    require(x.ok&&x.pos.at(0)>=11.7501,"flipped axis enforces larger physical gap");
    throws([&]{legalize_repair_axis(false,{"v"},{5},10,.3,
        {{false,"#anchor","v",.3,true,-1.}},fixed,{},2);},"invalid flipped separation gap");
    RepairSep projection{false,"#anchor","v",.3,true,-1.,false,true};
    const auto projected=legalize_repair_axis(false,{"v"},{5},10,.3,{projection},fixed,{},2);
    require(projected.ok&&projected.seps[0].gap==-1.&&projected.seps[0].projected_gap,
        "typed relative-entity adjustment must survive a repair flip");
    projection.flipped_gap=std::numeric_limits<double>::infinity();
    throws([&]{legalize_repair_axis(false,{"v"},{5},10,.3,{projection},fixed,{},2);},
        "invalid flipped separation gap");
}
void output_grid_contracts() {
    FloorplanLegalizeInput in;
    in.board_w=180;in.board_h=170;in.compact=true;
    in.fixed_rects={{"fmc",{53,45,114.63,63.685}}};
    in.fixed_poses["fmc"]={53,45};
    in.metrics["power_mon"]={{{"p",13,6}},{{"p",0,0,26.7565,12.1635}},{26.7565,12.1635}};
    in.metrics["fmc"]={{{"p",30,9}},{{"p",0,0,61.63,18.685}},{61.63,18.685}};
    in.index.hard.push_back({"flow_hop","power_mon","power_mon","fmc",100,"captured boundary",true,{},{}});
    in.primary_fanout["power_mon"]={{0,0,1.75,1.75},{.2995,.3,.3,.3},1};
    in.primary_fanout["fmc"]={{1.75,0,1.25,0},{.3,5.6,.3,.045},1};
    std::vector<FloorplanLegalizeVar> vars{{"power_mon",26.7565,12.163500000000001,{87.5435,30},87.5435,30}};
    std::vector<std::string> log;
    QuantizationCounts counts;
    require(floorplan_legalize_compact_accounted(in,vars,log,counts),"captured boundary compacts on output grid");
    require(vars[0].y+vars[0].h+1.45<=45,"exact forward physical inequality, no epsilon");
    require(vars[0].y==31.3864,"closest conservative representable boundary");
    require(counts.at("legalize_bound_precision4dp")>0,"actual bound quantization is recorded");

    // Lower-bound projection must round in the opposite direction.
    in={};in.board_w=60;in.board_h=60;in.compact=true;
    in.fixed_rects={{"anchor",{20,10,30,20.12345}}};in.fixed_poses["anchor"]={20,10};
    in.metrics["v"]={{{"p",5,5}},{{"p",0,0,10,10}},{10,10}};
    in.metrics["anchor"]=in.metrics.at("v");
    in.index.hard.push_back({"flow_hop","v","v","anchor",100,"lower boundary",true,{},{}});
    in.primary_fanout["v"]={{},{},1};in.primary_fanout["anchor"]={{},{},1};
    vars={{"v",10,10,{20,30},20,30}};log.clear();
    const bool lower_ok=floorplan_legalize_compact(in,vars,log);
    if(!lower_ok)for(const auto& entry:log)std::cerr<<entry<<'\n';
    require(lower_ok,"lower boundary compacts");
    require(vars[0].y==20.4235&&20.12345+.3<=vars[0].y,"lower boundary rounds outward from obstacle");

    // A continuous feasible point need not exist on the output lattice.
    in.index={};in.metrics.clear();in.fixed_poses.clear();in.primary_fanout.clear();
    // A harmless enforced self term activates composition without introducing
    // an additional geometric restriction or a pull toward either obstacle.
    in.metrics["v"]={{{"p",5,5}},{{"p",0,0,10,10}},{10,10}};
    in.index.hard.push_back({"near_max","v","v","v",100,"grid feasibility",true,{},{}});
    in.fixed_rects={{"below",{0,0,60,20.00004}},{"above",{0,30.60004,60,60}}};
    for(const auto* name:{"v","below","above"})in.primary_fanout[name]={{},{},1};
    vars={{"v",10,10,{20,20.30004},20,20.30004}};const auto initial=vars;log.clear();
    const bool empty_ok=floorplan_legalize_compact(in,vars,log);
    if(empty_ok){std::cerr<<"empty witness returned "<<vars[0].x<<","<<vars[0].y<<'\n';
        for(const auto& entry:log)std::cerr<<entry<<'\n';}
    require(!empty_ok,"empty output-grid interval must reject");
    require(vars[0].x==initial[0].x&&vars[0].y==initial[0].y,"failed grid repair leaves caller pose untouched");
    in.clear=.5;in.fixed_rects={{"below",{0,0,60,20}},{"above",{0,31,60,60}}};
    vars={{"v",10,10,{20,20.5},20,20.5}};log.clear();
    require(floorplan_legalize_compact(in,vars,log)&&vars[0].y==20.5,
            "genuinely feasible exact equality stays feasible and unchanged");
}
void mutations() {
    FloorplanInput in; in.som.w=10; in.som.h=8;
    in.footprints["dip"]={"dip",sexpr_loads(R"((footprint "dip" (fp_rect (start -4 -2) (end 4 2) (layer "F.CrtYd") (width 0.05)) (pad "1" thru_hole circle (at -3 0) (size 0.8 0.8)) (pad "2" thru_hole circle (at 3 0) (size 0.8 0.8))))")};
    in.geometry.resolvable["U1"]="dip"; in.geometry.bbox_of["U1"]={-4,-2,4,2};
    Engine e(in); FloorplanZoneShape s; s.w=12;s.h=8;s.top_off["U1"]={5,4};
    QuantizationCounts zone_counts;
    const auto pads=e.zone_components(s,true,&zone_counts),body=e.zone_components(s,false,&zone_counts);
    require(pads.size()==2 && body.size()==1,"pad-only and whole-body punch paths differ");
    require(std::abs(pads[0].dx-1.6)<1e-9 && std::abs(pads[0].w-.8)<1e-9 && pads[0].mask==3,"THT pad exact punch");
    require(body[0].dx==1 && body[0].dy==2 && body[0].w==8 && body[0].h==4 && body[0].mask==3,"conservative body punch");
    s.bot_off=s.top_off;s.top_off.clear();s.side="bottom";
    require(e.zone_components(s,true,&zone_counts).front().mask==1,"secondary face is opposite bottom primary");
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
    throws([&]{no_pad_at.zone_components(s,true,&zone_counts);},"pad kernel found none");
    broken=in;broken.footprints["dip"].source="opaque-provider/Fiducial_1mm.kicad_mod";
    Engine fiducial(broken);const auto fid_halo=fiducial.fanout(s);
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
        const bool packed=e.attempt_pack(false);
        require(packed==(width>102.2),"complete pack enforces edge-run width floor");
        const auto& first=e.plan.edge_blocks[0];const auto& second=e.plan.edge_blocks[1];
        require(first.edge=="S"&&second.edge=="S","width rejection does not silently change edge membership");
        if(packed)require(first.x==12&&first.y==108.5&&std::abs(second.x-52.3)<1e-12&&second.y==108.5,"frozen feasible edge-run poses");
        else require(first.x==a.x&&first.y==a.y&&second.x==b.x&&second.y==b.y,
                     "overflowing edge run must not publish infeasible poses");
    }
    in.som.w=20;in.som.h=20;
    // Isolate actual seating/refinement from later legalization: the hard
    // connector distance supplies a necessary domain even for a side hint.
    std::map<std::pair<bool,std::string>,FloorplanPoint> forward_edge_poses;
    for(const bool reversed:{false,true})for(const bool edge_target:{false,true})for(const bool shaped:{false,true})for(const std::string hint:{"E","N","S","W"}) {
        if(reversed&&!edge_target)continue; // Edge-to-interior authored terms.
        auto constrained=in;SomJGeom jack;jack.ref="J2";jack.x=0;jack.y=5;jack.w=2;jack.h=10;
        constrained.som.js={jack};
        FloorplanTerm term;term.kind="near_max";term.subject="logic";term.target_raw=edge_target?"connector":"som_j2";term.bound=5;
        if(reversed)std::swap(term.subject,term.target_raw);
        constrained.compose.index.hard={term};
        constrained.compose.metrics["logic"].pad_union={{"U1",0,0,10,10}};
        if(shaped)constrained.compose.shape_metrics[{"logic",1}].pad_union={{"U1",1,1,9,9}};
        if(edge_target)constrained.compose.metrics["connector"].pad_union={{"J1",2,2,8,8}};
        Engine e(constrained);e.board_size(100,80);
        FloorplanBlock b;b.name="logic";b.kind="interior";b.zone=hint;
        e.plan.interior_blocks={b};e.zbox={{"logic",{10,10}}};
        if(edge_target) {
            FloorplanBlock edge;edge.name="connector";edge.kind="edge";edge.edge="W";
            e.plan.edge_blocks={edge};e.zbox["connector"]={10,10};e.edge_of["connector"]="W";
        }
        if(shaped) {
            Shape alternate;alternate.w=alternate.h=10;alternate.side="bottom";
            e.shape_sets[e.plan.punch_free?1:0]["logic"]={alternate,alternate};e.owned_shape_choices["logic"]=1;
        }
        require(e.attempt_pack(false),"side-hinted constrained block must find the available left slot");
        const auto& placed=e.plan.interior_blocks.front();
        if(edge_target) {
            const auto key=std::make_pair(shaped,hint);
            const FloorplanPoint point{placed.x,placed.y};
            if(reversed)require(point==forward_edge_poses.at(key),
                "reversing a symmetric proximity term changes seating/refinement");
            else forward_edge_poses[key]=point;
        }
        Box4 target{e.plan.som_x,e.plan.som_y+5,e.plan.som_x+2,e.plan.som_y+15};
        if(edge_target) {
            const auto& edge=e.plan.edge_blocks.front();
            target={edge.x+2,edge.y+2,edge.x+8,edge.y+8};
        }
        const auto domain=near_translation_domain(shaped?Box4{1,1,9,9}:Box4{0,0,10,10},target,5,occ_step);
        require(placed.shape_idx==(shaped?1:0),"hard-domain fixture lost selected-shape coverage");
        require(placed.x>=domain.x0&&placed.x<=domain.x1&&placed.y>=domain.y0&&placed.y<=domain.y1,
                "side hint bypassed hard connector proximity during seating/refinement");
    }
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
        {"outline_snap_up",20},{"run_overflow_tol",696},{"som_pose_half_mm",1390},{"quant_credit",696},{"est_via_cost",2}};
    // Restoring each screened plan removes two redundant SoM-coordinate
    // quantizations per pass; all actually executed calls still count.
    require(floorplan_precision_fixture::select(automatic.accounting.quantization_engagements,false)==quanta,"all prior synthetic search quantization engagements accounted exactly");
    const auto extra=floorplan_precision_fixture::select(automatic.accounting.quantization_engagements);
    require(extra.at("floorplan_candidate_area_precision1dp")==118&&extra.at("floorplan_seed_aspect_precision4dp")==1,
            "both passes count 55 accepted candidates plus four objective-bound probes, and one seed aspect");
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
    auto bottom=top;bottom.side="bottom";
    auto mixed_top=top;mixed_top.bot_off=mixed_top.top_off;mixed_top.top_off.clear();
    auto mixed_bottom=mixed_top;mixed_bottom.side="bottom";
    in.geometry.shapes["sink"]={top,bottom,mixed_top,mixed_bottom};
    for(bool impedance:{false,true}) {
        if(impedance)in.impedance_net_classes["signal"]="DP100_TMDS";
        Engine e(in);e.prepare_cross();
        FloorplanBlock a,b;a.name="source";b.name="sink";a.w=a.h=b.w=b.h=2;b.x=3;b.y=4;
        e.plan.interior_blocks={a,b};
        require(e.estimate()==5,"hand-computed 3-4-5 cross-subsystem MST");
        e.plan.interior_blocks[1].shape_idx=1;e.plan.interior_blocks[1].side="bottom";
        require(std::abs(e.estimate()-(impedance?12.6:7.2))<1e-12,"actual selected-bottom topology charges correct via class");
        e.plan.interior_blocks[1].shape_idx=2;e.plan.interior_blocks[1].side="top";
        require(std::abs(e.estimate()-(impedance?12.6:7.2))<1e-12,"top-primary alternate must charge its physical bottom pin transition");
        e.plan.interior_blocks[1].shape_idx=3;e.plan.interior_blocks[1].side="bottom";
        require(e.estimate()==5,"bottom-primary alternate must not charge a physical top pin transition");
        const std::vector<const FloorplanBlock*> partial{&e.plan.interior_blocks[1]};
        require(e.estimate(partial,"sink")==0,"one-sheet partial estimator excludes absent endpoint");
        require(e.n_impedance==(impedance?1:0),"impedance split reflects source class, not sheet name");
        // Source has physical net endpoints but no alternate geometry table.
        // An unavailable selected shape must not silently score its base pose.
        for(int invalid:{-1,1,999}) {
            e.plan.interior_blocks[0].shape_idx=invalid;
            throws([&]{(void)e.estimate();},"no prepared geometry for U1001");
            const std::vector<const FloorplanBlock*> selected{&e.plan.interior_blocks[0],&e.plan.interior_blocks[1]};
            throws([&]{(void)e.estimate(selected,"sink");},"no prepared geometry for U1001");
        }
        e.plan.interior_blocks[0].shape_idx=0;
        require(e.estimate()==5,"base geometry remains valid after rejected selections");
        auto base_bottom=in;base_bottom.geometry.side_of["U2001"]="bottom";
        base_bottom.geometry.bot_off["sink"]=base_bottom.geometry.top_off.at("sink");base_bottom.geometry.top_off.erase("sink");
        Engine base(base_bottom);base.prepare_cross();base.plan.interior_blocks={a,b};
        require(std::abs(base.estimate()-(impedance?12.6:7.2))<1e-12,"base bottom endpoint must charge its transition without selecting a variant");
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
void current_plan_requirements(const FloorplanInput& in,const FloorplanPlan& result) {
    Engine source(in);source.initialize();source.prepare_geometry();
    std::map<std::string,FloorplanBlock> expected;
    for(const auto* b:source.blocks())expected.emplace(b->name,*b);
    std::set<std::string> seen;
    require(std::isfinite(result.board_w)&&std::isfinite(result.board_h)&&
            result.board_w>0&&result.board_h>0,"current outline finite and positive");
    source.board_size(result.board_w,result.board_h);
    require(result.som_x==source.plan.som_x&&result.som_y==source.plan.som_y&&
            result.som.w==in.som.w&&result.som.h==in.som.h,"source module dimensions and placement policy");
    std::vector<PairsBlock> interiors,edges;
    for(const auto* blocks:{&result.interior_blocks,&result.edge_blocks})for(const auto& b:*blocks) {
        require(expected.count(b.name)&&seen.insert(b.name).second,"unique source block identity");
        const auto& base=expected.at(b.name);
        require(b.kind==base.kind&&b.n_parts==base.n_parts,"source block kind and part count");
        double w=source.zbox.at(b.name).first,h=source.zbox.at(b.name).second;
        auto reach=base.fanout_reach,inset=base.fanout_inset;
        std::string side="top";
        require(b.shape_idx>=0,"nonnegative selected shape");
        if(b.shape_idx) {
            const auto& shape=in.geometry.shapes.at(b.name).at(static_cast<std::size_t>(b.shape_idx));
            w=shape.w;h=shape.h;side=shape.side;
            std::tie(reach,inset)=source.fanout(shape);
        }
        require(b.w==w&&b.h==h&&b.side==side,"selected source shape dimensions and side");
        same(halo_json(b.fanout_reach),halo_json(reach),"selected reach");
        same(halo_json(b.fanout_inset),halo_json(inset),"selected inset");
        require(std::isfinite(b.x)&&std::isfinite(b.y)&&b.x>=0&&b.y>=0&&
                b.x+b.w<=result.board_w&&b.y+b.h<=result.board_h,"block inside current outline");
        const auto& pool=source.components[result.punch_free?1:0];
        const auto entry=pool.find({b.name,b.shape_idx});
        auto children=entry==pool.end()?std::vector<Comp>{}:entry->second;
        const int mask=b.kind=="edge"?(result.punch_free?occ_top:occ_punch):side_mask(b.side);
        if(b.kind=="edge") {
            require(b.edge.size()==1&&b.edge==source.edge_of.at(b.name),"source connector edge retained");
            children=result.punch_free?edge_components(b.edge.front(),b.x,b.y,result.board_w,
                result.board_h,occ_punch,children):std::vector<Comp>{};
            edges.push_back({b.x,b.y,b.w,b.h,reach,inset,mask,children});
        } else interiors.push_back({b.x,b.y,b.w,b.h,reach,inset,mask,children});
    }
    require(seen.size()==expected.size(),"every source block retained exactly once");
    require(result.dec_count==source.plan.dec_count&&result.dec_radius==source.plan.dec_radius,
            "source decoupling geometry retained");
    source.plan=result;
    const auto keepouts=source.som_keepouts();
    const double sx=result.som_x-som_pad,sy=result.som_y-som_pad;
    const auto children=result.punch_free?som_components(sx,sy,result.dec_radius,
        som_decoupling_cells(result.som_x,result.som_y,result.som.w,result.som.h,result.dec_count,dec_inset),
        {keepouts.begin()+1,keepouts.end()},occ_bottom,occ_punch):std::vector<Comp>{};
    require(pairs_hold_from_layout(interiors,edges,sx,sy,result.som.w+2*som_pad,result.som.h+2*som_pad,
        result.punch_free?occ_top:occ_punch,children,result.board_w,result.board_h,mh_corner,occ_punch,clear),
        "selected primary and child occupancy satisfy actual physical clearances");
    const double estimate=experiment_metric_contracts::estimate(in,result);
    bool winner=false;
    for(const auto& d:result.accounting.decisions)if(d.name=="sizing_winner") {
        winner=true;const auto inputs=jobject(d.inputs);
        require(num(inputs,"est_cross")==estimate,"winner estimate matches independent current geometry");
        require(estimate<=num(inputs,"budget"),"current layout fits electrical length budget");
        require(std::abs(num(inputs,"headroom")-(num(inputs,"budget")-estimate))<1e-9,
                "headroom uses current geometry");
    }
    require(winner,"complete current sizing decision");
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
    for(const auto& jack:e.plan.som.js) {
        FloorplanBlock block;block.name="near_som_probe";block.zone="@som_j"+jack.ref.substr(1);
        const auto anchor=e.anchor_row(block,{});
        require(!anchor.zone_is_at_edge,"SoM target must not masquerade as a perimeter connector");
        require(anchor.zone_ax==e.plan.som_x+jack.x+jack.w/2&&
                anchor.zone_ay==e.plan.som_y+jack.y+jack.h/2,"explicit SoM connector anchor fell back to E");
    }
    const auto geometry=parse_json_file((dir/(name+"_geometry.json")).string());
    for(const auto& row:geometry.array_value) {
        const auto sheet=str(row,"sheet");const int k=static_cast<int>(num(row,"index"));
        Halo reach,inset;
        if(k)std::tie(reach,inset)=e.fanout(in.geometry.shapes.at(sheet).at(k));
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
    // Historical cross_estimate omitted base-bottom and mixed-top transitions.
    // Keep those source fixtures unchanged, but judge the same frozen geometry
    // with the independent physical-pad/MST oracle, not the obsolete score.
    require(std::abs(e.estimate()-experiment_metric_contracts::estimate(in,e.plan,false))<1e-8,
            name+": frozen geometry estimate matches independent physical-side oracle");
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
    require(markdown.find(".py")==std::string::npos,name+": current floorplan Markdown has no obsolete Python source paths");
    require(markdown.find("native/src/constraints.cpp")!=std::string::npos &&
            markdown.find("native/src/power_checks.cpp")!=std::string::npos,
            name+": current floorplan cites native electrical producers");
    for(const auto& note:notes)
        require(note.short_text.find(".py")==std::string::npos && note.long_text.find(".py")==std::string::npos,
                name+": current placement notes have no obsolete Python source paths");
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
    const auto result=build_floorplan(in);
    current_plan_requirements(in,result);
    // Repeatability is same-input/current-code reproducibility, not historical
    // poses. Exact ledger equality here includes all actually executed work;
    // instrumented receipt suites independently detect dropped/duplicate calls.
    const auto repeated=build_floorplan(in);
    same(floorplan_plan_json(result),floorplan_plan_json(repeated),name+": current repeatability");
    for(int mutation=0;mutation<7;++mutation) {
        auto bad=result;
        if(mutation==0)bad.interior_blocks.pop_back();
        if(mutation==1)bad.interior_blocks.front().x=-1;
        if(mutation==2)bad.interior_blocks.front().w+=1;
        if(mutation==3)bad.interior_blocks.push_back(bad.interior_blocks.front());
        if(mutation==4) {
            bool changed=false;
            for(auto& d:bad.accounting.decisions)if(d.name=="sizing_winner")
                for(auto& [key,value]:d.inputs)if(key=="est_cross"){value.number_value+=1;changed=true;}
            require(changed,"mutation must reach the winner estimate");
        }
        if(mutation==5) {
            const auto hit=std::find_if(bad.interior_blocks.begin(),bad.interior_blocks.end(),
                [](const auto& b){return b.side=="top";});
            require(hit!=bad.interior_blocks.end(),"physical collision mutation has a top body");
            hit->x=bad.som_x;hit->y=bad.som_y;
        }
        if(mutation==6)bad.board_w=std::numeric_limits<double>::quiet_NaN();
        bool rejected=false;
        try {current_plan_requirements(in,bad);}catch(const std::exception&){rejected=true;}
        require(rejected,"corrupt source geometry or estimate must reject");
    }
    const auto documents=render_floorplan_documents(result,in);
    const auto repeated_documents=render_floorplan_documents(repeated,in);
    require(documents.svg==repeated_documents.svg&&documents.markdown==repeated_documents.markdown,
            name+": current document repeatability");
    const auto seed=render_floorplan_spec_json(result);
    require(seed==render_floorplan_spec_json(repeated),name+": current seed repeatability");
    TemporaryOutput publication;
    const auto paths=write_floorplan_documents(documents,publication.directory);
    require(paths==std::vector<std::filesystem::path>{publication.directory/"FLOORPLAN.svg",publication.directory/"FLOORPLAN.md"},
            name+": explicit published paths");
    require(read_bytes(paths[0])==documents.svg&&read_bytes(paths[1])==documents.markdown,name+": publication matches current documents");
    const auto seed_path=publication.directory/"floorplan.json";
    require(write_floorplan_spec(result,seed_path)==seed_path&&read_bytes(seed_path)==seed,name+": publication matches current seed");
    require(load_floorplan_spec(seed_path.string())->names().size()==result.edge_blocks.size()+result.interior_blocks.size(),
            name+": exported spec reloads every subsystem");
    const FloorplanDocuments replacement{{},"replacement SVG\n","replacement Markdown\n",{}};
    write_floorplan_documents(replacement,publication.directory);
    require(read_bytes(paths[0])==replacement.svg&&read_bytes(paths[1])==replacement.markdown,name+": replaces existing documents");
    throws([&]{write_floorplan_documents(documents,paths[0]);},"filesystem");
    require(!load_floorplan_spec((publication.directory/"missing.json").string()),name+": missing optional spec");
}
void repair_choice_contracts() {
    {
        FloorplanLegalizeInput in;in.board_w=20;in.board_h=20;
        in.fixed_rects={{"obstacle",{0,0,20,20}}};
        in.metrics["v"]={{{"p",1,1}},{{"p",0,0,2,2}},{2,2}};
        in.som_j_rects["som_j1"]={9,9,10,10};
        in.index.hard.push_back({"near_max","v","v","som_j1",1,"cycle geometry witness",true,{},{}});
        const std::vector<FloorplanLegalizeVar> initial{{"v",2,2,{10,10},10,10}};
        auto quiet=initial,loud=initial;std::vector<std::string> quiet_log,loud_log;
        QuantizationCounts quiet_counts,loud_counts;
        require(!floorplan_legalize_compact_accounted(in,quiet,quiet_log,quiet_counts),"fully occupied board must fail");
        in.report_infeasible_cycle=true;
        require(!floorplan_legalize_compact_accounted(in,loud,loud_log,loud_counts),"diagnostic mode changed infeasibility");
        const auto contains=[&](const auto& lines,const std::string& text){return std::any_of(lines.begin(),lines.end(),[&](const auto& line){return line.find(text)!=std::string::npos;});};
        require(contains(loud_log,"cycle seed:")&&contains(loud_log,"#obstacle [0.0,0.0,20.0,20.0]")&&
                contains(loud_log,"v [10.0,10.0,12.0,12.0]"),"cycle diagnostic lost fixed or moving seed geometry");
        require(!contains(quiet_log,"cycle seed:")&&quiet_counts==loud_counts&&quiet[0].x==loud[0].x&&quiet[0].y==loud[0].y,
                "cycle diagnostics changed accounting or poses, or leaked while disabled");
    }
    const Box4 moving{-3,-2,5,4},target{10,20,12,28};
    const auto domain=near_translation_domain(moving,target,2,0);
    require(domain.x0==3&&domain.x1==17&&domain.y0==14&&domain.y1==32,"near domain must use asymmetric pad extents");
    std::size_t feasible=0;
    for(int x=-20;x<=30;++x)for(int y=-20;y<=40;++y) {
        const auto gap_x=std::max({0.,target.x0-(x+moving.x1),x+moving.x0-target.x1});
        const auto gap_y=std::max({0.,target.y0-(y+moving.y1),y+moving.y0-target.y1});
        if(std::hypot(gap_x,gap_y)<=2) {
            ++feasible;require(x>=domain.x0&&x<=domain.x1&&y>=domain.y0&&y<=domain.y1,
                "near domain excluded a physically feasible pad-hull translation");
        }
    }
    require(feasible>0,"near-domain oracle was vacuous");
    require(std::hypot(target.x0-(domain.x0+moving.x1),target.y0-(domain.y0+moving.y1))>2,
        "a domain corner may still fail Euclidean distance and needs the final gate");
    const auto contact=near_translation_domain({0,0,0,0},target,0,0);
    require(contact.x0==target.x0&&contact.y0==target.y0&&contact.x1==target.x1&&contact.y1==target.y1,
        "zero-distance point domain must preserve closed contact bounds");
    const auto guarded=near_translation_domain({0,0,.3,1},{.1,0,1,1},2,.05);
    const double closed_x=-2.2;
    require(.1-(closed_x+.3)==2&&closed_x>=guarded.x0,"cancellation excluded an accepted closed-boundary grid point");
    throws([&]{near_translation_domain(moving,target,-1,0);},"nonnegative");
    throws([&]{near_translation_domain({3,0,2,1},target,2,0);},"ordered");
    throws([&]{near_translation_domain(moving,target,std::numeric_limits<double>::infinity(),0);},"finite");
    throws([&]{near_translation_domain(moving,{1e308,0,1e308,1},1e308,0);},"not finite");
    throws([&]{near_translation_domain(moving,target,2,-1);},"nonnegative");
    for(const bool directional_gap:{false,true}) {
        FloorplanLegalizeInput in;in.board_w=60;in.board_h=60;in.compact=true;
        in.metrics["v"]={{{"p",5,5}},{{"p",0,0,10,10}},{10,10}};
        in.som_j_rects["som_j1"]={25,42,26,43};
        in.index.hard.push_back({"near_max","v","v","som_j1",5,"perpendicular-order witness",true,{},{}});
        in.fixed_rects={{"obstacle",{20,20,30,30}}};
        if(directional_gap) {
            in.primary_fanout["v"]={{.4,.8,4.5,.9},{},1};
            in.primary_fanout["obstacle"]={{.2,.3,.4,1.25},{},1};
        }
        std::vector<FloorplanLegalizeVar> vars{{"v",10,10,{5,30},5,30}};
        std::vector<std::string> log;
        const bool ok=floorplan_legalize_compact(in,vars,log);
        if(!ok)for(const auto& line:log)std::cerr<<line<<'\n';
        require(ok,"perpendicular-order repair rescues the lower slot");
        require(vars[0].y>=(directional_gap?34.5:30.3),"flipped body must respect reversed directional gap");
        require(std::count(log.begin(),log.end(),"retry: flipped separations follow perpendicular seed order")==1,
            "perpendicular order must execute once and be recorded");
        auto repeat=std::vector<FloorplanLegalizeVar>{{"v",10,10,{5,30},5,30}};
        std::vector<std::string> second_log;
        require(floorplan_legalize_compact(in,repeat,second_log)&&second_log==log&&
            repeat[0].x==vars[0].x&&repeat[0].y==vars[0].y,"perpendicular repair must be deterministic");
    }
    const std::vector<std::string> names{"a","b"};
    const std::vector<double> sizes{2,2};
    const std::vector<RepairSep> seps{{true,"a","b",1,true,2},{true,"b","a",1,true,3}};
    const auto run=[&](std::vector<std::size_t> path){return legalize_repair_axis(true,names,sizes,20,0,seps,{}, {},4,path);};
    const auto ordinary=run({}),first=run({0}),second=run({1}),repeat=run({1});
    auto reversed_seps=seps;
    for(auto& s:reversed_seps){s.reverse_on_flip=true;s.flipped_gap=7;}
    const auto reversed=legalize_repair_axis(true,names,sizes,20,0,reversed_seps,{}, {},4,{0});
    require(reversed.ok&&reversed.seps.back().lo==first.seps.back().hi&&
        reversed.seps.back().hi==first.seps.back().lo&&reversed.seps.back().gap==7&&
        !reversed.seps.back().flippable&&!reversed.seps.back().reverse_on_flip,
        "primitive reversal must retain selected directional gap and lock the result");
    require(ordinary.ok&&first.ok&&second.ok,"both eligible cycle branches must solve X");
    require(ordinary.infeasible_cycle.empty(),"successful repair retained a stale cycle");
    auto locked=seps;for(auto& sep:locked)sep.flippable=false;
    const auto infeasible=legalize_repair_axis(true,names,sizes,20,0,locked,{}, {},4);
    require(!infeasible.ok&&infeasible.fail=="cycle"&&infeasible.infeasible_cycle.size()==2,
        "locked contradictory pair needs an actual terminal cycle witness");
    require(infeasible.infeasible_cycle_origins.size()==2,"cycle provenance lost an edge");
    require(infeasible.infeasible_cycle_separations.size()==2&&
        std::set<int>(infeasible.infeasible_cycle_separations.begin(),infeasible.infeasible_cycle_separations.end())==std::set<int>{0,1},
        "cycle provenance lost stable input separation indices");
    for(const auto& origin:infeasible.infeasible_cycle_origins)
        require(origin=="separation a -> b"||origin=="separation b -> a","cycle provenance lost separation identity");
    std::map<std::string,int> balance;double cycle_cost=0;
    for(const auto& edge:infeasible.infeasible_cycle) {
        ++balance[edge.src];--balance[edge.dst];cycle_cost+=edge.cost;
        require(((edge.src=="a"&&edge.dst=="b")||(edge.src=="b"&&edge.dst=="a"))&&edge.cost==-3,
            "cycle witness invented an edge or changed its exact bound");
    }
    for(const auto& [name,count]:balance){(void)name;require(count==0,"cycle witness is not closed");}
    require(cycle_cost==-6,"cycle witness does not independently prove negative total cost");
    const auto exhausted=legalize_repair_axis(true,names,sizes,20,0,seps,{}, {},0);
    require(!exhausted.ok&&exhausted.fail=="exhausted"&&exhausted.infeasible_cycle.empty(),
        "unexecuted budget-exhausted solve must not invent cycle evidence");
    require(exhausted.flips.empty()&&exhausted.choice_counts.empty()&&
        exhausted.seps[0].axis_x&&exhausted.seps[1].axis_x,
        "zero repair budget executed a flip");
    const std::vector<RepairSep> two_cycles{{true,"a","b",1,true},{true,"b","a",1,true},
        {true,"c","d",1,true},{true,"d","c",1,true}};
    for(int budget=0;budget<=3;++budget) {
        const auto bounded=legalize_repair_axis(true,{"a","b","c","d"},{2,2,2,2},20,0,two_cycles,{}, {},budget);
        require(bounded.flips.size()==static_cast<std::size_t>(std::min(budget,2))&&
            bounded.choice_counts.size()==bounded.flips.size(),"repair exceeded its exact flip budget");
        require(bounded.ok==(budget>=2),"two independent cycles require exactly two flips");
        if(budget<2)require(bounded.fail=="exhausted"&&bounded.pos.empty()&&bounded.infeasible_cycle.empty(),
            "budget exhaustion published positions or false infeasibility evidence");
    }
    const auto no_repair=legalize_repair_axis(true,{"a"},{2},20,0,{}, {}, {},0);
    require(no_repair.ok&&no_repair.flips.empty()&&no_repair.pos.size()==1,
        "zero budget must still accept an already feasible axis");
    std::vector<std::string> many_names;std::vector<double> many_sizes;std::vector<RepairSep> many_cycles;
    for(int i=0;i<17;++i) {
        const auto a="a"+std::to_string(i),b="b"+std::to_string(i);
        many_names.push_back(a);many_names.push_back(b);many_sizes.push_back(2);many_sizes.push_back(2);
        many_cycles.push_back({true,a,b,1,true});many_cycles.push_back({true,b,a,1,true});
    }
    for(int budget:{16,17}) {
        const auto bounded=legalize_repair_axis(true,many_names,many_sizes,20,0,many_cycles,{}, {},budget);
        require(bounded.flips.size()==static_cast<std::size_t>(budget)&&bounded.ok==(budget==17),
            "configured sixteen-flip limit must not execute a seventeenth repair");
    }
    require(first.choice_counts==std::vector<std::size_t>{2}&&second.choice_counts==first.choice_counts,
        "cycle alternatives not reported exactly");
    require(ordinary.pos==first.pos&&ordinary.flips==first.flips&&ordinary.fail==first.fail,
        "default first-choice repair changed");
    require(first.flips!=second.flips&&second.flips==repeat.flips&&second.pos==repeat.pos,
        "explicit alternative ignored or not deterministic");
    for(const auto* result:{&first,&second}) {
        require(result->flips.size()==1&&result->seps.size()==2,"branch silently added flips or removed constraints");
        const auto& moved=result->seps.back();
        require(!moved.axis_x&&!moved.flippable&&moved.flipped_gap==1&&
            moved.gap==(moved.lo=="a"?2:3),"branch lost directional gap or flip lock");
    }
    throws([&]{(void)run({2});},"choice outside");
    require(seps[0].axis_x&&seps[1].axis_x&&seps[0].flippable&&seps[1].flippable,
        "branch mutated caller separation state");
}
void joint_separation_contracts() {
    const auto domain=[](const std::string& a,const std::string& b){
        return std::vector<RepairSep>{{true,a,b,1},{false,a,b,1},{true,b,a,1},{false,b,a,1}};
    };
    const std::vector<std::vector<RepairSep>> domains{domain("a","b"),domain("a","#obstacle"),domain("b","#obstacle")};
    const auto apart=[](double ax,double ay,double bx,double by){return ax+3<=bx||bx+3<=ax||ay+3<=by||by+3<=ay;};
    std::size_t solved=0,impossible=0,capped=0;
    for(int w=5;w<=9;++w)for(int h=5;h<=9;++h){
        // Integer dimensions, gaps and bounds give integral difference-system
        // solutions. Exhaustive coordinate enumeration is independent of the
        // negative-cycle search and its separation/domain selection.
        bool oracle=false;
        for(int ax=0;ax<=w-2;++ax)for(int ay=0;ay<=h-2;++ay)
            for(int bx=0;bx<=w-2;++bx)for(int by=0;by<=h-2;++by)
                oracle|=apart(ax,ay,bx,by)&&apart(ax,ay,2,2)&&apart(bx,by,2,2);
        for(std::size_t budget:{1u,4u,16u,64u}){
            const auto run=[&]{return legalize_joint_separations({"a","b"},{2,2},{2,2},w,h,0,domains,{{"obstacle",{2,2,4,4}}},{},{},budget);};
            const auto r=run(),repeat=run();
            require(r.generated<=budget&&r.visited<=r.generated&&r.visited>0&&r.axis_solves>=r.visited&&r.axis_solves<=2*r.visited,
                "joint search exceeded generated-state budget or miscounted axis probes");
            require(r.domain_probes<=budget&&r.domain_rejections<=r.domain_probes&&
                    r.domain_probes==repeat.domain_probes&&r.domain_rejections==repeat.domain_rejections,
                    "unary pruning exceeded independent probe cap or lost reproducibility");
            require(r.ok==repeat.ok&&r.complete==repeat.complete&&r.budget_exhausted==repeat.budget_exhausted&&
                r.generated==repeat.generated&&r.visited==repeat.visited&&r.axis_solves==repeat.axis_solves&&r.choices==repeat.choices&&r.x==repeat.x&&r.y==repeat.y,
                "joint search is not reproducible");
            if(budget==64)require(r.ok==oracle&&!r.budget_exhausted&&(r.ok||r.complete),"complete domain search disagrees with coordinate oracle");
            if(r.ok){
                ++solved;require(oracle&&r.x.size()==2&&r.y.size()==2&&r.choices.size()==3,"joint search published invalid solution shape");
                for(int i=0;i<2;++i)require(r.x[i]>=0&&r.y[i]>=0&&r.x[i]+2<=w&&r.y[i]+2<=h,"joint pose exceeds walls");
                require(apart(r.x[0],r.y[0],r.x[1],r.y[1])&&apart(r.x[0],r.y[0],2,2)&&apart(r.x[1],r.y[1],2,2),
                    "independent physical separation check rejects joint solution");
                const auto pos=[&](const std::string& n,bool x){return n=="#obstacle"?2.:(x?r.x[n=="a"?0:1]:r.y[n=="a"?0:1]);};
                for(std::size_t i=0;i<domains.size();++i){const auto& s=domains[i].at(r.choices[i]);
                    require(pos(s.lo,s.axis_x)+2+s.gap<=pos(s.hi,s.axis_x),"joint result violates its selected directed alternative");}
            } else {
                require(r.x.empty()&&r.y.empty()&&r.choices.empty(),"failed search leaked speculative poses");
                require(r.complete!=r.budget_exhausted,"failed search conflated exhaustion and capped exploration");
                if(r.complete){++impossible;require(!oracle,"joint search falsely proved supplied domains infeasible");}else ++capped;
            }
        }
    }
    require(solved&&impossible&&capped,"joint oracle missed a success, exhausted search or capped search");
    const std::vector<std::vector<RepairSep>> directional{{{true,"a","b",1},{false,"a","b",3},{false,"b","a",5}}};
    const auto reversed=legalize_joint_separations({"a","b"},{2,2},{2,2},4,12,0,directional,{}, {},{{"a","#0",-8},{"#0","b",0}},4);
    require(reversed.ok&&reversed.choices==std::vector<std::size_t>{2}&&reversed.y[0]>=reversed.y[1]+7,
        "coupled solver failed to reverse with the explicitly supplied directional gap");
    const auto blocked=legalize_joint_separations({"a","b"},{2,2},{2,2},4,12,0,directional,{}, {},{{"#0","a",6},{"#0","b",0}},4);
    require(!blocked.ok&&blocked.complete&&!blocked.budget_exhausted,"reversed direction incorrectly reused a smaller gap");
    const auto incumbent=legalize_joint_separations({"a"},{2},{2},10,10,0,{}, {},{},{},1);
    const auto pruned=legalize_joint_separations({"a","b"},{2,2},{2,2},4,10,0,{domain("a","b")},{},
        {},{{"a","#0",-8},{"#0","b",0}},2);
    require(pruned.ok&&pruned.choices==std::vector<std::size_t>{3}&&pruned.generated==2&&pruned.visited==2&&
            pruned.domain_probes==2&&pruned.domain_rejections==2&&pruned.axis_solves==3,
            "unary contradictions consumed assignment budget or unprobed feasible direction was excluded");
    auto forward=RepairSep{true,"a","b",-1,false};forward.projected_gap=true;
    auto backward=RepairSep{true,"b","a",-1,false};backward.projected_gap=true;
    const auto projected=legalize_joint_separations({"a","b"},{2,2},{2,2},3,2,0,{{forward,backward}}, {},
        {{"a","#0",-1},{"#0","b",0}}, {},2);
    require(projected.ok&&projected.choices==std::vector<std::size_t>{1}&&projected.domain_probes==1&&
            projected.domain_rejections==0&&projected.x==std::vector<double>{1,0},
            "unary pruning lost explicitly projected signed separation gaps");
    for(int lower:{0,2,4})for(int upper:{0,2,4}){
        bool oracle=false;
        for(int ax=0;ax<=4;++ax)for(int ay=lower;ay<=4;++ay)
            for(int bx=0;bx<=4;++bx)for(int by=0;by<=upper;++by)
                oracle|=apart(ax,ay,bx,by)&&apart(ax,ay,2,2)&&apart(bx,by,2,2);
        const auto bounded=legalize_joint_separations({"a","b"},{2,2},{2,2},6,6,0,domains,
            {{"obstacle",{2,2,4,4}}},{},{{"a","#0",-double(lower)},{"#0","b",double(upper)}},64);
        require(bounded.ok==oracle&&(bounded.ok||bounded.complete),"unary hard-bound pruning disagrees with independent coordinate oracle");
    }
    require(incumbent.ok&&incumbent.visited==1&&incumbent.generated==1&&incumbent.axis_solves==2&&incumbent.x==std::vector<double>{0}&&incumbent.y==incumbent.x,
        "already feasible joint incumbent did extra work or moved");
    const auto hard=legalize_joint_separations({"a"},{2},{2},10,10,0,{}, {},{{"#0","a",0},{"a","#0",-1}},{},5);
    require(!hard.ok&&hard.complete&&hard.visited==1&&hard.axis_solves==1,"hard-only negative cycle needs no geometric retries");
    throws([&]{legalize_joint_separations({"a"},{2},{2},10,10,0,{}, {},{},{},0);},"state limit");
    throws([&]{legalize_joint_separations({"a"},{2},{2},10,10,0,{{}}, {},{},{},1);},"empty domain");
    throws([&]{legalize_joint_separations({"a"},{2},{2},10,10,0,{{{true,"a","unknown",1}}}, {},{},{},1);},"pair domain");
    throws([&]{legalize_joint_separations({"a"},{2},{2},10,10,0,{}, {},{{"unknown","a",0}},{},1);},"additional edge");
    throws([&]{legalize_joint_separations({"a"},{2},{2},10,10,0,{},{{"a",{0,0,1,1}}},{},{},1);},"fixed rectangle");
    throws([&]{legalize_joint_separations({"a"},{2},{2},10,10,0,{}, {},{},{},std::numeric_limits<std::size_t>::max());},"state limit");
    throws([&]{legalize_joint_separations({"a","b"},{1e308,1e308},{2,2},1e308,10,0,{{{true,"a","b",1e308}}}, {},{},{},1);},"nonfinite derived edge");
    throws([&]{legalize_joint_separations({"a"},{2},{2},10,10,0,{}, {},{{"#0","a",std::numeric_limits<double>::infinity()}},{},1);},"additional edge");
    throws([&]{legalize_joint_separations({"a"},{2},{2},10,10,0,{},{{"obstacle",{0,0,std::numeric_limits<double>::quiet_NaN(),1}}},{},{},1);},"fixed rectangle");
    JointSeparationWork receipt{99,99,99,true};
    throws([&]{legalize_joint_separations({"a","b"},{1e308,1e308},{2,2},1e308,10,0,{{{true,"a","b",1e308}}}, {},{},{},1,&receipt);},"nonfinite derived edge");
    require(receipt.generated==1&&receipt.visited==1&&receipt.axis_solves==0&&!receipt.budget_exhausted,
        "exception receipt lost prepared state or claimed an unexecuted axis solve");
    throws([&]{legalize_joint_separations({"a","b"},{1e308,1e308},{2,2},1e308,10,0,
        {{{true,"a","b",0},{true,"b","a",1e308}}}, {},{},{},2,&receipt);},"nonfinite derived edge");
    require(receipt.visited==1&&receipt.axis_solves==1&&receipt.domain_probes==0&&receipt.domain_rejections==0,
            "unary preparation overflow lost executed root work or invented an unexecuted probe");
    throws([&]{legalize_joint_separations({"a"},{2},{2},10,10,0,{}, {},{},{},0,&receipt);},"state limit");
    require(receipt.generated==0&&receipt.visited==0&&receipt.axis_solves==0,"invalid invocation retained a stale receipt");
    const std::vector<std::vector<RepairSep>> qualify_domain{domain("a","b")};
    std::size_t qualified=0;
    const auto later=legalize_joint_separations({"a","b"},{2,2},{2,2},10,10,0,qualify_domain,{}, {},{},4,&receipt,
        [&](const auto& choices,const auto&,const auto&){++qualified;return choices[0]==2;});
    require(later.ok&&later.choices[0]==2&&qualified==3&&receipt.qualifications==3&&receipt.qualification_rejections==2,
        "qualification rejection failed to continue or lost its actual work");
    const auto rejected=legalize_joint_separations({"a","b"},{2,2},{2,2},10,10,0,qualify_domain,{}, {},{},4,&receipt,
        [](const auto&,const auto&,const auto&){return false;});
    require(!rejected.ok&&rejected.complete&&rejected.x.empty()&&receipt.qualifications==4&&receipt.qualification_rejections==4,
        "all-rejected qualification published a proposal or misreported exhaustion");
    throws([&]{legalize_joint_separations({"a","b"},{2,2},{2,2},10,10,0,qualify_domain,{}, {},{},4,&receipt,
        [](const auto&,const auto&,const auto&)->bool{throw std::runtime_error("qualifier stop");});},"qualifier stop");
    require(receipt.visited==1&&receipt.axis_solves==2&&receipt.qualifications==1&&receipt.qualification_rejections==0,
        "throwing qualifier lost executed prefix or invented a rejection verdict");
    std::cout<<"joint separation oracle PASS solved="<<solved<<" exhausted="<<impossible<<" capped="<<capped<<'\n';
}
void joint_composer_contracts(){
    std::size_t recovered=0,preserved=0,failed=0;
    std::array<std::size_t,4> recovered_modes{};
    std::optional<FloorplanLegalizeInput> witness;
    std::vector<FloorplanLegalizeVar> witness_vars;
    for(int mode:{0,1,2,3})for(int row:{4,8,12})for(int column:{4,8,12})for(int x:{3,8,13})for(int y:{3,8,13}){
        FloorplanLegalizeInput in;in.board_w=24;in.board_h=24;in.compact=true;
        in.fixed_rects={{"horizontal",{8.,double(row),14.,double(row+3)}},{"vertical",{double(column),8.,double(column+3),16.}}};
        in.metrics["v"]={{{"p",1.5,1.5}},{{"p",0,0,3,3}},{3,3}};
        in.som_j_rects["som_j1"]={11,11,13,13};
        in.index.hard.push_back({"near_max","v","v","som_j1",7,"joint fixture",true,{},{}});
        if(mode){
            in.primary_fanout["v"]={{.4,1.2,.8,1.6},{},1,1,std::vector<Comp>{}};
            in.primary_fanout["horizontal"]={{.5,1.7,1.1,.6},{},1,1,std::vector<Comp>{}};
            in.primary_fanout["vertical"]={{1.3,.4,.7,1.5},{},1,1,std::vector<Comp>{}};
            if(mode>=2){
                in.primary_fanout["horizontal"].mask=2;in.primary_fanout["horizontal"].occupied_mask=2;
                in.primary_fanout["v"].occupied_mask=3;
                Comp child;child.dx=1.25;child.dy=1.5;child.w=.75;child.h=.5;child.mask=mode==3?3:2;child.reach={.2,.4,.3,.1};
                in.primary_fanout["v"].children=std::vector<Comp>{child};
            }
        }
        const std::vector<FloorplanLegalizeVar> initial{{"v",3,3,{double(x),double(y)},double(x),double(y)}};
        auto legacy=initial,candidate=initial;std::vector<std::string> first_log,second_log;QuantizationCounts first_counts,second_counts;
        const bool before=floorplan_legalize_compact_accounted(in,legacy,first_log,first_counts);
        in.joint_separation_states=128;std::size_t starts=0,ends=0;JointSeparationWork work;
        in.joint_retry_started=[&]{++starts;};in.joint_retry_completed=[&](const auto& w,bool){++ends;work=w;};
        const bool after=floorplan_legalize_compact_accounted(in,candidate,second_log,second_counts);
        if(before){++preserved;require(after&&starts==0&&ends==0&&legacy[0].x==candidate[0].x&&legacy[0].y==candidate[0].y&&first_counts==second_counts&&first_log==second_log,
            "joint retry replaced a successful incumbent or its work");}
        else{
            require(starts==1&&ends==1&&work.generated<=128&&work.visited<=work.generated,"joint retry lost boundaries or exceeded budget");
            if(after){++recovered;++recovered_modes[mode];
                if(!witness){witness=in;witness->joint_retry_started={};witness->joint_retry_completed={};witness_vars=initial;}
                const auto& v=candidate[0];require(v.x>=in.clear&&v.y>=in.clear&&v.x+v.w+in.clear<=24&&v.y+v.h+in.clear<=24,"joint composer violated walls");
                const auto separated=[&](const Box4& a,const Halo& ar,const Box4& b,const Halo& br){
                    return a.x1+std::max({in.clear,ar.e,br.w})<=b.x0||b.x1+std::max({in.clear,br.e,ar.w})<=a.x0||
                        a.y1+std::max({in.clear,ar.s,br.n})<=b.y0||b.y1+std::max({in.clear,br.s,ar.n})<=a.y0;
                };
                for(const auto& fixed:in.fixed_rects){const auto& b=fixed.second;
                    const auto ar=mode?in.primary_fanout.at("v").reach:Halo{},br=mode?in.primary_fanout.at(fixed.first).reach:Halo{};
                    if(mode>=2&&fixed.first=="horizontal")
                        require(separated({v.x+1.25,v.y+1.5,v.x+2,v.y+2},{.2,.4,.3,.1},b,br),"independent bottom-child clearance rejected joint result");
                    else require(separated({v.x,v.y,v.x+v.w,v.y+v.h},ar,b,br),"independent directional fanout rejected joint result");
                    if(mode==3)require(separated({v.x+1.25,v.y+1.5,v.x+2,v.y+2},{.2,.4,.3,.1},b,br),"through-hole reservation must clear both faces");
                }
                for(const auto& t:floorplan_evaluate_terms(in,{{"v",{v.x,v.y}}}))require(!t.term.enforced||t.ok,"joint composer accepted a red term");
            }else{++failed;require(candidate[0].x==initial[0].x&&candidate[0].y==initial[0].y,"failed joint composer published partial placement");}
        }
    }
    require(recovered&&preserved&&std::all_of(recovered_modes.begin(),recovered_modes.end(),[](auto n){return n>0;}),
        "joint composer fixtures missed a physical mode or incumbent preservation");
    auto interrupted=witness_vars;std::vector<std::string> log;QuantizationCounts counts;
    witness->joint_retry_completed=[](const auto&,bool){throw std::runtime_error("joint observer stop");};
    throws([&]{floorplan_legalize_compact_accounted(*witness,interrupted,log,counts);},"joint observer stop");
    require(interrupted[0].x==witness_vars[0].x&&interrupted[0].y==witness_vars[0].y&&!counts.empty(),"joint observer exception lost work or published placement");
    std::cout<<"joint composer PASS recovered="<<recovered<<" preserved="<<preserved<<" rejected="<<failed
             <<" plain="<<recovered_modes[0]<<" directional="<<recovered_modes[1]<<" mixed="<<recovered_modes[2]<<" through="<<recovered_modes[3]<<'\n';
}
}  // namespace
int main(int argc,char** argv) {
    try {
        const std::filesystem::path dir=argc>1 ? argv[1]:"native/tests/data/floorplan";
        const bool geometry_only=argc>2 && std::string(argv[2])=="--geometry-only";
        repair_choice_contracts();
        joint_separation_contracts();
        joint_composer_contracts();
        facing_projection_contracts();
        compose_contracts(dir);primary_fanout_contracts();output_grid_contracts();mutations();pack_behavior();cross_behavior();frozen(dir,"devkit_mini",geometry_only);frozen(dir,"carrier",geometry_only);
        std::cout<<"floorplan contracts: "<<checks<<" checks passed"<<(geometry_only ? " (geometry/estimator slice)":"")<<"\n";
        return 0;
    } catch (const std::exception& e) { std::cerr<<"floorplan contracts: "<<e.what()<<"\n";return 1; }
}
