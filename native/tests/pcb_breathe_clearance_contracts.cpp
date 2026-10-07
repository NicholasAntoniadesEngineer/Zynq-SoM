#include "pcb_placement_fixture.hpp"
#include "pcb_placement_internal.hpp"
#include <iomanip>
#include <iostream>
#include <sstream>

namespace {
using namespace schgen;
using schgen::pcb_placement::Placer;
using schgen::pcb_placement::Offsets;
using namespace placement_fixture;
std::size_t checks = 0, failures = 0;
void require(bool ok, const std::string& message) {
    ++checks;
    if (!ok) { ++failures; std::cerr << "FAIL " << message << '\n'; }
}
Box4 united(Box4 a, Box4 b) {
    return {std::min(a.x0,b.x0),std::min(a.y0,b.y0),
            std::max(a.x1,b.x1),std::max(a.y1,b.y1)};
}
double gap(Box4 a, Box4 b) {
    // Signed axis separation: preserve penetration as well as positive gaps.
    return std::max({a.x0-b.x1,b.x0-a.x1,a.y0-b.y1,b.y0-a.y1});
}
std::string precise(double value) {
    std::ostringstream out;out<<std::setprecision(17)<<value;return out.str();
}
Box4 translated(Box4 b, FloorplanPoint p) {
    return {b.x0+p.first,b.y0+p.second,b.x1+p.first,b.y1+p.second};
}
struct Replay {
    PcbPlacementInput in;
    PcbZoneResult zones;
    FloorplanStage stage;
    PcbModel model;
    J snapshots;
    std::unique_ptr<Placer> p;
    std::map<std::string,Box4> occupied;
    std::set<std::string> through, locked;
    Replay(const std::filesystem::path& root, const std::string& name, bool compact,
           bool reverse) {
        // Same immutable inputs/helpers as pcb_placement_fixture.hpp. Do not
        // call load(): its interface/mapping tail reads live project hardware.
        const auto base=root/"native/tests/data";
        const auto fp=parse_json_file((base/"floorplan"/(name+".json")).string());
        const auto& input=field(fp,"input");
        const auto emit=parse_json_file((base/"pcb_emit"/(name+".json")).string());
        const auto trace=parse_json_file((base/"pcb_placement"/(name+"_placement.json")).string());
        snapshots=field(trace,"snapshots");
        const auto geo=parse_json_file((base/"pcb_placement"/(name+"_geometry.json")).string());
        const auto& g=field(geo,"geometry");
        const auto authored=parse_json_file((base/"pcb_placement"/(name+"_authored.json")).string());
        const auto& a=field(authored,"authored");
        for(const auto& [path,bytes]:field(emit,"footprints").object_value)
            zones.footprints[path]=pcb_check_footprint(path,bytes.string_value);
        model=pcb_model_from_json(field(emit,"model"),zones.footprints);
        for(const auto& s:field(input,"sheets").array_value)
            in.floorplan.sheets.push_back(decode_intermediate_circuit_ir(s));
        for(const auto& [s,index]:field(input,"sheet_index").object_value)
            in.floorplan.sheet_index.emplace_back(s,static_cast<int>(index.number_value));
        const auto& placement=field(field(a,"project"),"placement");
        in.floorplan.project.wired_sheets=strings(field(placement,"wired_sheets"));
        in.floorplan.project.pilot_prox_sheets=strings(field(placement,"pilot_prox_sheets"));
        in.floorplan.compact_search=compact;
        for(const auto& [s,c]:field(a,"contracts").object_value) in.contracts[s]=c;
        const auto& expected=field(fp,"expected");
        const auto& plan=field(expected,"plan");
        stage.plan.board_w=number(expected,"board_w");
        stage.plan.board_h=number(expected,"board_h");
        stage.plan.som=som(field(plan,"som"));
        stage.plan.som_x=number(plan,"som_x");stage.plan.som_y=number(plan,"som_y");
        for(const auto& [s,refs]:field(g,"refs_by_sheet").object_value)
            zones.geometry.refs_by_sheet[s]=strings(refs);
        zones.geometry.mh_refs=strings(field(g,"mh_refs"));
        for(const auto& [r,edge]:field(g,"conn_edge").object_value)
            zones.geometry.conn_edge[r]=edge.string_value;
        const auto& entry=field(snapshots,"edge_seat");
        // Emission adds fiducials later; they are not breathe participants.
        model.insts.erase(std::remove_if(model.insts.begin(),model.insts.end(),
            [&](const auto& inst){return !object_field(entry,inst.ref);}),model.insts.end());
        for(auto& inst:model.insts) {
            const auto& row=field(entry,inst.ref).array_value;
            inst.x=inst.y=0;inst.rotation=row.at(2).number_value;
            if(reverse) inst.side=inst.side=="top"?"bottom":"top";
            zones.geometry.resolvable[inst.ref]=inst.mod->source;
            zones.geometry.bbox_of[inst.ref]=*inst.mod->bbox;
            zones.geometry.side_of[inst.ref]=inst.side;
            zones.footprints[inst.mod->source]=inst.mod;
            for(const auto& pad:inst.mod->pads)
                if(std::get<1>(pad)=="thru_hole" || std::get<1>(pad)=="np_thru_hole")
                    through.insert(inst.ref);
        }
        p=std::make_unique<Placer>(in,zones,stage);
        for(const auto* key:{"edge_blocks","interior_blocks"})
            for(const auto& b:field(plan,key).array_value)
                p->origins[string(b,"name")]={number(b,"x"),number(b,"y")};
        const PcbCheckInput physical(model);
        for(std::size_t i=0;i<model.insts.size();++i) {
            const auto& inst=model.insts[i];
            p->pos[inst.ref]=point(field(entry,inst.ref));
            p->rotations[inst.ref]=inst.rotation;
            occupied[inst.ref]=united(physical.courtyard_at(i),physical.pad_bbox_at(i));
            const auto& part=p->ctx.by_ref.at(inst.ref);
            if(part.sheet.rfind("som_j",0)==0) p->som_refs[inst.ref]=part.sheet;
            const bool mount=std::find(zones.geometry.mh_refs.begin(),zones.geometry.mh_refs.end(),inst.ref)!=zones.geometry.mh_refs.end();
            if(mount || part.sheet.rfind("som_j",0)==0 || part.sheet=="som_decoupling" ||
               part.footprint.find("Fiducial")!=std::string::npos ||
               zones.geometry.conn_edge.count(inst.ref) || p->contract_members.count(inst.ref) ||
               (p->ctx.wired.count(part.sheet) && in.contracts.count(part.sheet)) ||
               (compact && p->ctx.l4_exempt.count(part.sheet))) locked.insert(inst.ref);
        }
        require(p->pos.size()==entry.object_value.size(),name+" full frozen population");
    }
    double separation(const Offsets& positions,const std::string& a,const std::string& b) const {
        return gap(translated(occupied.at(a),positions.at(a)),translated(occupied.at(b),positions.at(b)));
    }
    void compare(const Offsets& before,const std::string& label) const {
        std::size_t pairs=0,cross=0,preexisting=0;
        for(auto i=occupied.begin();i!=occupied.end();++i)
            for(auto j=std::next(i);j!=occupied.end();++j) {
                const auto& a=i->first;const auto& b=j->first;
                if(p->side(a)!=p->side(b)) {
                    if(!through.count(a) && !through.count(b)) continue;
                    ++cross;
                }
                ++pairs;
                const double old=separation(before,a,b),now=separation(p->pos,a,b);
                if(old<in.floorplan.place_clear) ++preexisting;
                // Deliberately no epsilon and no testpoint/sheet exemptions.
                require(now>=std::min(in.floorplan.place_clear,old),label+" "+a+"/"+b+
                    " gap "+precise(old)+" -> "+precise(now));
            }
        for(const auto& r:locked) require(p->pos.at(r)==before.at(r),label+" locked "+r);
        std::cout<<label<<" pairs="<<pairs<<" cross_face_THT="<<cross
                 <<" preexisting="<<preexisting<<" locked="<<locked.size()<<'\n';
    }
};
void run(const std::filesystem::path& root,const std::string& name,bool compact,bool reverse) {
    Replay f(root,name,compact,reverse);
    const std::string label=name+(compact?" compact":" default")+(reverse?" reversed":" original");
    const auto entry=f.p->pos;
    const auto rotations=f.p->rotations;
    const auto sides=f.p->geometry.side_of;
    const auto boxes=f.p->geometry.bbox_of;
    const auto pool=f.p->ctx.pool;
    for(const auto* phase:{"A","B"}) {
        const auto before=f.p->pos;
        const auto counts=f.p->ctx.quantization;
        f.p->breathe(phase);
        f.compare(before,label+"/"+phase);
        require(f.p->rotations==rotations && f.p->geometry.side_of==sides && f.p->ctx.pool==pool,
                label+" fixed orientation/source");
        for(const auto& [r,b]:boxes) {
            const auto q=f.p->geometry.bbox_of.at(r);
            require(b.x0==q.x0 && b.y0==q.y0 && b.x1==q.x1 && b.y1==q.y1,label+" fixed bbox "+r);
        }
        for(const auto& [k,n]:counts) require(f.p->ctx.quantization.at(k)>=n,label+" retained actual-work receipt "+k);
    }
    f.compare(entry,label+"/edge_seat->breathe");
    std::size_t moved=0;
    for(const auto& [r,xy]:entry) if(f.p->pos.at(r)!=xy) ++moved;
    require(moved>0,label+" must exercise accepted movement");
    require(f.p->pos.size()==entry.size(),label+" population unchanged");
    require(f.p->geometry.bbox_of.size()==boxes.size(),label+" geometry population unchanged");
    require(f.p->ctx.quantization.at("breathe_grid_extent")==8,label+" two grids in each of two phases");
    // Small explicit actual-work receipt contract, not a replacement golden
    // layout: rejected trials/rollback must retain both coordinate calls.
    require(f.p->ctx.quantization.at("breathe_commit_precision")==
            (name=="carrier"?88u:20u),label+" rounded trial coordinate receipts");
    std::cout<<label<<" moved="<<moved<<" receipts";
    for(const auto& [k,n]:f.p->ctx.quantization) {
        require(n>0,label+" fabricated zero receipt "+k);
        std::cout<<' '<<k<<'='<<n;
    }
    std::cout<<'\n';
    if(name=="carrier" && !compact && !reverse) {
        Offsets historical;
        for(const auto& [r,row]:field(f.snapshots,"breathe").object_value) historical[r]=point(row);
        for(const auto& pair:std::vector<std::pair<std::string,std::string>>{
                {"C1004","C1005"},{"C1005","R1001"},
                {"TP5002","TP5003"},{"TP5002","TP5008"},{"TP5007","TP5008"},
                {"TP5003","U5006"},{"TP5004","U5006"},{"TP5005","U5007"}}) {
            const double before=f.separation(entry,pair.first,pair.second);
            const double old=f.separation(historical,pair.first,pair.second);
            require(before>=.5 && old<.5,"historical physical negative control "+pair.first+"/"+pair.second);
            std::cout<<"historical-physical-witness "<<pair.first<<'/'<<pair.second<<' '
                     <<before<<" -> "<<old<<" guarded="<<f.separation(f.p->pos,pair.first,pair.second)<<'\n';
        }
        for(const auto& r:{"U1002","TP1001","U5006","U5007"}) {
            const auto old=point(field(field(f.snapshots,"breathe"),r)),now=f.p->pos.at(r);
            std::cout<<"frozen-witness "<<r<<" old="<<old.first<<','<<old.second
                     <<" new="<<now.first<<','<<now.second<<'\n';
        }
        std::cout<<"physical-witness U1002/TP1001 "<<f.separation(entry,"U1002","TP1001")
                 <<" -> "<<f.separation(f.p->pos,"U1002","TP1001")<<'\n';
    }
}
}
int main(int argc,char** argv) {
    try {
        if(argc!=2) throw std::runtime_error("usage: pcb_breathe_clearance_contracts REPOSITORY");
        std::cout<<std::setprecision(17);
        for(const auto* name:{"carrier","devkit_mini"})
            for(bool compact:{false,true}) for(bool reverse:{false,true}) run(argv[1],name,compact,reverse);
        std::cout<<(failures?"FAIL ":"PASS ")<<checks<<" checks; "<<failures<<" failures; 8 frozen replays, 16 phases\n";
        return failures?1:0;
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 2;}
}
