#include "pcb_checks_internal.hpp"
#include "schgen/precision_ops.hpp"
#include "schgen/place_search.hpp"
#include "schgen/board_decision_policy.hpp"

namespace schgen {
using namespace pcb_checks;
PlacementMechResult check_placement_mech(const PcbCheckInput& input){
    const auto& m=input.model();PlacementMechResult res;res.board_w=m.board_w;res.board_h=m.board_h;res.som_core=m.som_core;
    const auto direction_component=[&](double value){
        static const std::string name="mechanical_direction_component";
        checked_quantization_add(res.quantization_engagements,name);
        return mechanical_direction_component(value);
    };
    const std::map<std::string,std::pair<int,int>> outward={{"N",{0,-1}},{"S",{0,1}},{"W",{-1,0}},{"E",{1,0}}};
    for(std::size_t i=0;i<m.insts.size();++i){const auto& inst=m.insts[i];auto part=mpn(m.connectors,inst);if(part.empty()||!(m.connectors.at(part).edge_pinned||m.edge_sheets.count(inst.sheet))||mating_face_vector(m.connectors.at(part))==std::pair<int,int>{0,0})continue;++res.n_connectors;
        const auto b=input.courtyard_at(i);std::vector<std::pair<std::string,double>> distances={{"N",b.y0-m.origin_y},{"S",m.origin_y+m.board_h-b.y1},{"W",b.x0-m.origin_x},{"E",m.origin_x+m.board_w-b.x1}};
        auto edge=std::min_element(distances.begin(),distances.end(),[](const auto& a,const auto& b){return a.second<b.second;});
        const auto mating=mating_face_vector(m.connectors.at(part));auto vec=turn_point(mating.first,inst.mirror?-mating.second:mating.second,inst.rotation);std::pair<int,int> face{direction_component(vec.first),direction_component(vec.second)};
        bool on_edge=edge->second<=0.6,mouth=face==outward.at(edge->first),ok=on_edge&&mouth;
        res.connectors.push_back({inst.ref,part,edge->first,inst.rotation,edge->second,face,ok});
        if(!ok){std::vector<std::string> why;if(!on_edge)why.push_back("interior ("+f(edge->second,1)+"mm > 0.6mm off the "+edge->first+" edge)");if(!mouth)why.push_back("mouth "+pair_repr(face)+" faces inward (off-board for the "+edge->first+" edge is "+pair_repr(outward.at(edge->first))+")");res.bad_connectors.push_back(inst.ref+" ("+inst.sheet+") "+part+": "+join(why,"; "));}
    }
    if(m.som_core)for(std::size_t i=0;i<m.insts.size();++i){const auto& inst=m.insts[i];auto b=input.courtyard_at(i);
        if(overlap_area(b,*m.som_core)<=0.5)continue;auto filename=std::filesystem::path(inst.mod->source).filename().string();
        if(starts(filename,"MountingHole")||starts(filename,"Fiducial")||!inst.module_connector.empty()||inst.side=="bottom")continue;
        auto row=inst.ref+" ("+inst.sheet+") "+inst.value+" [TOP]: courtyard ("+f(b.x0,1)+","+f(b.y0,1)+")..("+f(b.x1,1)+","+f(b.y1,1)+") overlaps SoM core — carrier TOP under the module is a keepout";
        auto prefix=ref_prefix(inst.ref);bool passive=(prefix=="R"||prefix=="C"||prefix=="L")&&!starts(inst.ref,"RS")&&!starts(inst.ref,"RJ")&&!starts(inst.ref,"LED");
        if(passive){res.top_under_som.push_back(row);continue;}res.under_som.push_back(row);if(prefix=="SW"||prefix=="BT")res.controls_under_som.push_back(row);
    }
    for(const auto& inst:m.insts){auto p=ref_prefix(inst.ref);bool face=p=="TP"||p=="LED"||p=="SW"||inst.footprint.find("TestPoint")!=std::string::npos||starts(inst.footprint,"LED_")||starts(inst.footprint,"Switch:");if(!face)continue;++res.n_face_top;if(inst.side=="bottom")res.face_top_on_bottom.push_back(inst.ref+" ("+inst.sheet+") "+inst.value+" ["+inst.footprint+"] emits B.Cu — a user-facing part must present on the top face");}
    res.ok=res.bad_connectors.empty()&&res.under_som.empty()&&res.controls_under_som.empty()&&res.top_under_som.empty()&&res.face_top_on_bottom.empty();return res;
}
std::string PlacementMechResult::summary()const{
    std::vector<std::string> l={"LAW-6 PLACEMENT (mechanical) GATE: "+verdict(ok)+" (board "+g(board_w)+" x "+g(board_h)+" mm)"};if(som_core){auto s=*som_core;l.push_back("  SoM module-body core: ("+f(s.x0,1)+","+f(s.y0,1)+")..("+f(s.x1,1)+","+f(s.y1,1)+") mm — bottom-passives-only, TOP keepout");}
    l.push_back("  off-board connectors: "+std::to_string(n_connectors)+" ("+std::to_string(bad_connectors.size())+" mis-placed)");
    for(const auto& r:connectors)l.push_back("    "+std::string(r.ok?"OK ":"BAD")+" "+pad(r.ref,9)+" "+pad(r.mpn,16)+" edge="+r.edge+" rot="+pad(f(r.rotation,0),3,true)+" mouth->"+pair_repr(r.face_dir)+" flush="+f(r.flush,1)+"mm");
    for(const auto& s:bad_connectors)l.push_back("    MISPLACED "+s);
    l.push_back("  non-passive parts under SoM core: "+std::to_string(under_som.size()));for(const auto& s:under_som)l.push_back("    UNDER-SoM "+s);
    l.push_back("  controls under SoM core: "+std::to_string(controls_under_som.size()));for(const auto& s:controls_under_som)l.push_back("    CONTROL-UNDER-SoM "+s);
    l.push_back("  carrier TOP parts under SoM core (keepout): "+std::to_string(top_under_som.size()));for(const auto& s:top_under_som)l.push_back("    TOP-UNDER-SoM "+s);
    l.push_back("  user-facing parts (TP/LED/SW): "+std::to_string(n_face_top)+" ("+std::to_string(face_top_on_bottom.size())+" face-down)");for(const auto& s:face_top_on_bottom)l.push_back("    FACE-DOWN "+s);return join(l);
}
// Both policy conditions are required. Pad count alone previously exempted
// dense ICs as both subjects and crowders; it is not connector identity.
bool pcb_is_df40_part(const std::string& module_connector,int pins){return pins>=board_decision_policy::df40_min_pins&&!module_connector.empty();}
std::set<std::string> pcb_module_sheets(const PcbCheckModel& model){std::set<std::string> sheets;for(const auto& inst:model.insts)if(!inst.module_connector.empty())sheets.insert(inst.sheet);return sheets;}
bool pcb_counts_as_crowder(const std::string& ref,const std::string& sheet,const std::string& module_connector,int pins,const std::string& footprint,const std::string& subject_sheet){return !(pcb_is_df40_part(module_connector,pins)||footprint.find("Fiducial")!=std::string::npos||is_testpoint_ref(ref)||(sheet==subject_sheet&&is_cluster_passive(ref,pins,{"RS","RJ","RN","LED"},{"R","C","L"})));}
std::pair<double,std::string> pcb_fanout_need(int pins){return intelligent_need(pins,{{2,0.2,"2-pin passive — escapes on its own pads"},{8,1.5,"<=8-pin non-passive — 1.5 mm absolute floor (user law 2026-07-29)"}},2,">=9-pin package — 2.0 mm floor (user law 2026-07-29)");}
PcbFanoutResult check_fanout_strict(const PcbCheckInput& input,std::optional<int> baseline){
    const auto& m=input.model();PcbFanoutResult res;std::vector<Box4> boxes;
    // fanout_gate.check deliberately reads every courtyard before filtering.
    for(std::size_t i=0;i<m.insts.size();++i)boxes.push_back(input.courtyard_at(i));
    for(std::size_t i=0;i<m.insts.size();++i){const auto& inst=m.insts[i];int pins=static_cast<int>(inst.pad_nets.size());if(pcb_is_df40_part(inst.module_connector,pins)||pins<3)continue;
        auto need=pcb_fanout_need(pins);std::vector<Box4> others;std::vector<std::size_t> indices;
        for(std::size_t j=0;j<m.insts.size();++j){const auto& o=m.insts[j];if(i!=j&&o.side==inst.side&&pcb_counts_as_crowder(o.ref,o.sheet,o.module_connector,static_cast<int>(o.pad_nets.size()),o.footprint,inst.sheet)){others.push_back(boxes[j]);indices.push_back(j);}}
        auto best=nearest_rect_gap(boxes[i],others,1e-4);
        std::string ref="(none)",sheet="-";if(best.index>=0){const auto& o=m.insts[indices.at(static_cast<std::size_t>(best.index))];if(!o.ref.empty())ref=o.ref;if(!o.sheet.empty())sheet=o.sheet;}
        res.records.push_back({inst.ref,inst.sheet,inst.side,pins,best.gap,need.first,ref,sheet,need.second});
    }
    std::stable_sort(res.records.begin(),res.records.end(),[](const auto& a,const auto& b){return a.slack()==b.slack()?a.ref<b.ref:a.slack()<b.slack();});
    res.n_subjects=static_cast<int>(res.records.size());for(const auto& r:res.records)if(r.starved())++res.n_starved;res.baseline=baseline.value_or(res.n_starved);res.ok=res.n_starved<=*res.baseline;
    if(!res.ok)for(const auto& r:res.records)if(r.starved())res.regressions.push_back(r.ref+" ("+r.sheet+") "+std::to_string(r.pins)+"pin: clr="+f(r.clearance,3)+" < need="+f(r.need,2));return res;
}
int pcb_fanout_ratchet(int n,std::optional<int> previous){return previous?std::min(*previous,n):n;}
std::pair<double,std::string> pcb_escape_need(int nets){return intelligent_need(nets,{{2,0.2,"<=2 nets — escapes on its own pads"},{8,1.5,"<=8-net part — 1.5 mm floor on its pin sides (user law 2026-07-29, refined 2026-11-11)"}},2,">=9-net part — 2.0 mm floor on its pin sides (user law 2026-07-29, refined 2026-11-11)");}
int pcb_escape_nets(const PcbCheckInstance& inst){std::set<std::string> nets;for(const auto& pad:inst.pad_nets)if(!pad.second.second.empty())nets.insert(pad.second.second);return static_cast<int>(nets.size());}
std::vector<PcbEscapePad> pcb_escape_pads(const PcbCheckInstance& inst,const PcbCheckGeometry& geometry){
    std::map<std::string,bool> through;
    if(inst.mod)for(const auto& pad:inst.mod->pads){const auto& type=std::get<1>(pad);through[std::get<0>(pad)]=through[std::get<0>(pad)]||type=="thru_hole"||type=="np_thru_hole";}
    std::vector<PcbEscapePad> pads;
    for(const auto& [name,box]:geometry.pad_boxes){const auto net=inst.pad_nets.find(name);const bool connected=net!=inst.pad_nets.end()&&!net->second.second.empty();
        pads.push_back({box,connected&&!(through[name]&&net->second.second==pcb_ground_plane_net)});}
    return pads;
}
PcbEscapeSides pcb_escape_sides(const Box4& court,const std::vector<PcbEscapePad>& pads,double tie){
    PcbEscapeSides sides;
    for(const auto& pad:pads){if(!pad.counted)continue;
        const double x=(pad.box.x0+pad.box.x1)/2,y=(pad.box.y0+pad.box.y1)/2;
        const std::array<double,4> reach{y-court.y0,court.y1-y,x-court.x0,court.x1-x};
        const double nearest=*std::min_element(reach.begin(),reach.end());
        sides.north=sides.north||reach[0]<=nearest+tie;sides.south=sides.south||reach[1]<=nearest+tie;
        sides.west=sides.west||reach[2]<=nearest+tie;sides.east=sides.east||reach[3]<=nearest+tie;}
    return sides;
}
bool pcb_crowds_escape(const Box4& subject,const PcbEscapeSides& sides,const Box4& crowder){
    const bool beside=crowder.x0>=subject.x1||crowder.x1<=subject.x0,above=crowder.y0>=subject.y1||crowder.y1<=subject.y0;
    if(!beside&&!above)return true;
    return (beside&&(crowder.x0>=subject.x1?sides.east:sides.west))||(above&&(crowder.y0>=subject.y1?sides.south:sides.north));
}
PcbFanoutResult check_fanout(const PcbCheckInput& input,std::optional<int> baseline){
    const auto& m=input.model();PcbFanoutResult res;std::vector<Box4> boxes;
    for(std::size_t i=0;i<m.insts.size();++i)boxes.push_back(input.courtyard_at(i));
    for(std::size_t i=0;i<m.insts.size();++i){const auto& inst=m.insts[i];int pins=static_cast<int>(inst.pad_nets.size());const int nets=pcb_escape_nets(inst);if(pcb_is_df40_part(inst.module_connector,pins)||nets<3)continue;
        auto need=pcb_escape_need(nets);const auto sides=pcb_escape_sides(boxes[i],pcb_escape_pads(inst,input.geometry_at(i)),pcb_escape_tie_mm);std::vector<Box4> others;std::vector<std::size_t> indices;
        for(std::size_t j=0;j<m.insts.size();++j){const auto& o=m.insts[j];if(i!=j&&o.side==inst.side&&pcb_counts_as_crowder(o.ref,o.sheet,o.module_connector,static_cast<int>(o.pad_nets.size()),o.footprint,inst.sheet)&&pcb_crowds_escape(boxes[i],sides,boxes[j])){others.push_back(boxes[j]);indices.push_back(j);}}
        auto best=nearest_rect_gap(boxes[i],others,1e-4);
        std::string ref="(none)",sheet="-";if(best.index>=0){const auto& o=m.insts[indices.at(static_cast<std::size_t>(best.index))];if(!o.ref.empty())ref=o.ref;if(!o.sheet.empty())sheet=o.sheet;}
        res.records.push_back({inst.ref,inst.sheet,inst.side,pins,best.gap,need.first,ref,sheet,need.second});
    }
    std::stable_sort(res.records.begin(),res.records.end(),[](const auto& a,const auto& b){return a.slack()==b.slack()?a.ref<b.ref:a.slack()<b.slack();});
    res.n_subjects=static_cast<int>(res.records.size());for(const auto& r:res.records)if(r.starved())++res.n_starved;res.baseline=baseline.value_or(res.n_starved);res.ok=res.n_starved<=*res.baseline;
    if(!res.ok)for(const auto& r:res.records)if(r.starved())res.regressions.push_back(r.ref+" ("+r.sheet+") "+std::to_string(r.pins)+"pin: clr="+f(r.clearance,3)+" < need="+f(r.need,2));return res;
}
std::string PcbFanoutResult::summary()const{
    std::vector<std::string> l={"FAN-OUT CLEARANCE GATE (D13, report-first ratchet): "+verdict(ok),"  multi-pin subjects: "+std::to_string(n_subjects)+"  starved: "+std::to_string(n_starved)+"  baseline(ratchet): "+(baseline?std::to_string(*baseline):"unset"),"  intelligent need = pin-count tier; clearance = min courtyard gap to nearest FOREIGN part","  cluster-aware: own-sheet 2-pin R/C/L excluded; DF40 plugs (som_j*, >=40-pin) excluded (no-inflate)","  OFFENDERS (starved, worst slack first):"};
    bool any=false;for(const auto& r:records)if(r.starved()){any=true;l.push_back("    STARVED "+pad(r.ref,9)+" "+pad(r.sheet,16)+" "+pad(std::to_string(r.pins),3,true)+"pin ["+r.side.substr(0,3)+"] clr="+f(r.clearance,3)+" need="+f(r.need,2)+" slack="+sign(r.slack(),3)+" nearest="+r.nearest_ref+" ("+r.nearest_sheet+")");}if(!any)l.push_back("    (none)");
    if(!regressions.empty()){l.push_back("  RATCHET REGRESSION ("+std::to_string(regressions.size())+" — starved count "+std::to_string(n_starved)+" > baseline "+(baseline?std::to_string(*baseline):"None")+"):");for(const auto& s:regressions)l.push_back("    REGRESSION: "+s);}
    int count=0;for(const auto& r:records)if(!r.starved()&&count<5){if(count++==0)l.push_back("  (tightest PASSING subjects:)");l.push_back("    ok      "+pad(r.ref,9)+" "+pad(r.sheet,16)+" "+pad(std::to_string(r.pins),3,true)+"pin clr="+f(r.clearance,3)+" need="+f(r.need,2)+" slack="+sign(r.slack(),3));}return join(l);
}
} // namespace schgen
