#include "schgen/pcb_owned_groups.hpp"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {
using namespace schgen;
int checks=0;
void require(bool b,const char* message){++checks;if(!b)throw std::runtime_error(message);}
PcbCheckFootprintPtr footprint(bool owner,bool thru=false) {
    const std::string size=owner?"4":"1";
    const std::string pin=owner?"5":"1";
    return pcb_check_footprint("owned-test", "(footprint \"owned-test\" (layer \"F.Cu\")"
        " (fp_rect (start -"+size+" -"+size+") (end "+size+" "+size+") (stroke (width 0.05) (type default)) (fill none) (layer \"F.CrtYd\"))"
        " (pad \""+pin+"\" "+(thru?"thru_hole":"smd")+" rect (at "+(owner?"3":"-0.5")+" 0) (size 0.5 0.5) "+(thru?"(drill 0.2)":"")+" (layers \"F.Cu\" \"B.Cu\"))"
        " (pad \"2\" smd rect (at -0.5 0.5) (size 0.5 0.5) (layers \"F.Cu\")))");
}
PcbCheckModel fixture() {
    PcbCheckModel m;m.origin_x=m.origin_y=0;m.board_w=60;m.board_h=50;
    m.net_numbers={{"V",1},{"GND",2}};
    for(const auto& ref:{"U1","U2","C1","C2","C3","SW1"}) {
        PcbCheckInstance p;p.ref=ref;p.side="top";p.footprint="owned-test";p.value=ref;
        const bool owner=p.ref[0]=='U';p.mod=footprint(owner,p.ref=="SW1");
        p.pad_nets[owner?"5":"1"]={1,"V"};p.pad_nets["2"]={2,"GND"};
        p.x=p.ref=="U1"?10:p.ref=="U2"?38:p.ref=="C1"?43:p.ref=="C2"?30:p.ref=="C3"?52:20;
        p.y=p.ref=="SW1"?30:p.ref=="C2"?35:10;m.insts.push_back(p);
    }
    return m;
}
std::vector<OwnedCapPlacement> requirements() {
    return {{"U1","5","C1","1","2","V","GND",OwnedCapRole::Bypass},
            {"U1","5","C2","1","2","V","GND",OwnedCapRole::Bypass},
            {"U1","5","C3","1","2","V","GND",OwnedCapRole::OutputBulk}};
}
// Independent rectangle oracle: enumerate separation axes from freshly prepared
// result geometry, rather than using constructor's translated-box cache.
void invariant(const PcbCheckModel& before,const OwnedGroupCandidate& candidate,double clearance) {
    const auto& after=candidate.model;require(before.insts.size()==after.insts.size(),"part population");
    require(after.board_w<=before.board_w&&after.board_h<=before.board_h,"zone does not expand");
    const PcbCheckInput p(after);
    const PcbCheckInput original(before);
    const auto pad_gap=[](const Box4& a,const Box4& b) {
        const double x=a.x1<b.x0?b.x0-a.x1:b.x1<a.x0?a.x0-b.x1:0;
        const double y=a.y1<b.y0?b.y0-a.y1:b.y1<a.y0?a.y0-b.y1:0;
        return std::sqrt(x*x+y*y);
    };
    for(std::size_t i:{std::size_t(2),std::size_t(3)}) {
        const auto measured=pad_gap(p.geometry_at(0).pad_boxes.at("5"),p.geometry_at(i).pad_boxes.at("1"));
        require(std::abs(candidate.owned_pad_gaps.at(after.insts[i].ref)-measured)<=1e-10,
                "reported quality differs from freshly prepared pad geometry");
        require(pad_gap(p.geometry_at(0).pad_boxes.at("5"),p.geometry_at(i).pad_boxes.at("1"))<=
                pad_gap(original.geometry_at(0).pad_boxes.at("5"),original.geometry_at(i).pad_boxes.at("1")),"independent owned-terminal objective");
    }
    for(std::size_t i=0;i<after.insts.size();++i) {
        const auto& a=after.insts[i];const auto& b=before.insts[i];
        require(a.ref==b.ref&&a.pad_nets==b.pad_nets&&a.side==b.side&&a.rotation==b.rotation&&a.mod==b.mod,"immutable identity/side/rotation");
        if(a.ref!="C1"&&a.ref!="C2")require(a.x==b.x&&a.y==b.y,"non-bypass/fixed pose");
        const auto box=p.courtyard_at(i);
        require(box.x0>=after.origin_x&&box.y0>=after.origin_y&&box.x1<=after.origin_x+after.board_w&&box.y1<=after.origin_y+after.board_h,"zone bounds");
        for(std::size_t j=0;j<i;++j) {
            const auto& other=after.insts[j];
            if(a.side!=other.side&&!has_thru_pads_from_text(a.mod->bytes)&&!has_thru_pads_from_text(other.mod->bytes))continue;
            const auto v=p.courtyard_at(j);
            require(box.x1+clearance<=v.x0||v.x1+clearance<=box.x0||box.y1+clearance<=v.y0||v.y1+clearance<=box.y0,"independent courtyard/THT occupancy");
        }
    }
    require(after.net_numbers==before.net_numbers,"net-number identity");
}
void tests() {
    const auto model=fixture();auto rows=requirements();
    OwnedGroupOptions o;o.compact=true;o.clearance=0.5;o.movable_caps={"C1","C2","C3"};o.fixed_refs={"SW1"};o.top_refs={"SW1"};
    const auto result=construct_owned_group_candidates(model,rows,o);
    require(!result.alternatives.empty()&&result.alternatives.size()<=2,"bounded actual alternatives");
    require(!result.quantization.empty(),"actual pose invocation receipts");
    // Two orders, two eligible bypass caps; per cap: one target plus twelve
    // boundary trials per other part, each calling the x and y scalar once.
    require(result.quantization.size()==1&&result.quantization.at("placement_member_pose_precision4dp")==
        2*2*(1+12*(model.insts.size()-1))*2,"independent exact invocation count, including duplicate/rejected trials");
    for(const auto& a:result.alternatives) {
        invariant(model,a,o.clearance);
        require(a.owned_pad_gaps.at("C1")<10,"explicit distant owner, not nearest U2 on same rail");
    }
    auto disabled=o;disabled.compact=false;
    const auto default_result=construct_owned_group_candidates(model,rows,disabled);
    require(default_result.alternatives.empty()&&default_result.quantization.empty(),"default unchanged and no receipts manufactured");
    auto blocked=o;blocked.movable_caps.clear();
    require(construct_owned_group_candidates(model,rows,blocked).alternatives.empty(),"no implicit permission");
    blocked=o;blocked.fixed_refs.insert("C1");blocked.fixed_refs.insert("C2");
    require(construct_owned_group_candidates(model,rows,blocked).alternatives.empty(),"fixed caps cannot move");
    const auto rejects=[&](const auto& m,const auto& r,const auto& options) {
        auto actual=construct_owned_group_candidates(m,r,options);
        require(actual.alternatives.empty()&&!actual.diagnostics.empty()&&actual.diagnostics.front().find("REJECTED")==0,"invalid input rejected");
    };
    auto bad=rows;bad.front().owner="missing";rejects(model,bad,o);
    bad=rows;bad.front().owner_pin="1";rejects(model,bad,o);
    bad=rows;bad.push_back(rows.front());rejects(model,bad,o);
    bad=rows;bad.front().return_pin="1";rejects(model,bad,o);
    auto changed=model;changed.insts[2].pad_nets["1"]={2,"V"};rejects(changed,rows,o);
    changed=model;changed.net_numbers["GND"]=1;for(auto& p:changed.insts)p.pad_nets["2"]={1,"GND"};rejects(changed,rows,o);
    changed=model;changed.insts.back().side="bottom";rejects(changed,rows,o);
    changed=model;changed.insts[2].mod=nullptr;rejects(changed,rows,o);
    changed=model;changed.insts[2].x=std::numeric_limits<double>::quiet_NaN();rejects(changed,rows,o);
    auto invalid=o;invalid.clearance=-1;rejects(model,rows,invalid);
    invalid=o;invalid.movable_caps.insert("SW1");rejects(model,rows,invalid);
    changed=model;changed.insts.back().x=changed.insts[0].x;changed.insts.back().y=changed.insts[0].y;
    require(construct_owned_group_candidates(changed,rows,o).alternatives.empty(),"unchanged fixed overlap never waived");
    auto bulk_only=rows;bulk_only.erase(bulk_only.begin(),bulk_only.begin()+2);
    auto bulk_options=o;bulk_options.movable_caps={"C3"};
    const auto bulk_result=construct_owned_group_candidates(model,bulk_only,bulk_options);
    require(bulk_result.alternatives.empty()&&bulk_result.quantization.empty(),"output bulk does not acquire bypass objective or work counts");
    changed=model;changed.insts[2].side="bottom";
    auto opposite=construct_owned_group_candidates(changed,rows,o);
    require(!opposite.alternatives.empty(),"same existing opposite-side eligibility retained");
    for(const auto& a:opposite.alternatives)invariant(changed,a,o.clearance);
    changed.insts[0].mod=footprint(true,true);
    auto thru=construct_owned_group_candidates(changed,rows,o);
    require(!thru.alternatives.empty(),"THT obstacle still permits local alternative");
    for(const auto& a:thru.alternatives)invariant(changed,a,o.clearance);
    changed=model;changed.insts[0].rotation=90;changed.insts[2].rotation=180;
    auto rotated=construct_owned_group_candidates(changed,rows,o);
    require(!rotated.alternatives.empty(),"rotated named-pad alternative");
    for(const auto& a:rotated.alternatives)invariant(changed,a,o.clearance);
    for(double angle:{0.,90.,180.,270.})for(double fractional:{0.00004,0.00006,0.00049,0.00051}) {
        changed=model;changed.insts[0].rotation=angle;changed.insts[2].rotation=angle;
        for(auto& p:changed.insts){p.x+=fractional;p.y+=fractional;}
        const auto trial=construct_owned_group_candidates(changed,rows,o);
        for(const auto& a:trial.alternatives)invariant(changed,a,o.clearance);
    }
    for(double translation:{-100.,25.,10000.,1000000.}) {
        changed=model;changed.origin_x+=translation;changed.origin_y+=translation;
        for(auto& p:changed.insts){p.x+=translation;p.y+=translation;}
        const auto trial=construct_owned_group_candidates(changed,rows,o);
        require(!trial.alternatives.empty(),"finite translated-frame alternatives");
        for(const auto& a:trial.alternatives)invariant(changed,a,o.clearance);
    }
    std::reverse(rows.begin(),rows.end());
    const auto shuffled=construct_owned_group_candidates(model,rows,o);
    require(shuffled.alternatives.size()==result.alternatives.size()&&shuffled.quantization==result.quantization,"declaration order deterministic");
    for(std::size_t i=0;i<result.alternatives.size();++i)
        for(std::size_t j=0;j<model.insts.size();++j)
            require(shuffled.alternatives[i].model.insts[j].x==result.alternatives[i].model.insts[j].x&&shuffled.alternatives[i].model.insts[j].y==result.alternatives[i].model.insts[j].y,"deterministic coordinates");
}
}
int main(){try{tests();std::cout<<"PASS "<<checks<<" owned-group assertions; qualitative proximity UNVERIFIED\n";}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
