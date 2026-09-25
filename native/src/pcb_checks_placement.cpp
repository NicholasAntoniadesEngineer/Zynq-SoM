#include "pcb_checks_internal.hpp"
#include "schgen/place_search.hpp"

namespace schgen {
using namespace pcb_checks;
PlacementMechResult check_placement_mech(const PcbCheckInput& input){
    const auto& m=input.model();PlacementMechResult res;res.board_w=m.board_w;res.board_h=m.board_h;res.som_core=m.som_core;
    const std::map<std::string,std::pair<int,int>> outward={{"N",{0,-1}},{"S",{0,1}},{"W",{-1,0}},{"E",{1,0}}};
    for(std::size_t i=0;i<m.insts.size();++i){const auto& inst=m.insts[i];auto part=mpn(inst);if(part.empty())continue;++res.n_connectors;
        const auto b=input.courtyard_at(i);std::vector<std::pair<std::string,double>> distances={{"N",b.y0-m.origin_y},{"S",m.origin_y+m.board_h-b.y1},{"W",b.x0-m.origin_x},{"E",m.origin_x+m.board_w-b.x1}};
        auto edge=std::min_element(distances.begin(),distances.end(),[](const auto& a,const auto& b){return a.second<b.second;});
        auto vec=turn_point(part=="XT60PW-M"?1:0,part=="XT60PW-M"?0:1,inst.rotation);std::pair<int,int> face{static_cast<int>(py_round(vec.first,0)),static_cast<int>(py_round(vec.second,0))};
        bool on_edge=edge->second<=0.6,mouth=face==outward.at(edge->first),ok=on_edge&&mouth;
        res.connectors.push_back({inst.ref,part,edge->first,inst.rotation,edge->second,face,ok});
        if(!ok){std::vector<std::string> why;if(!on_edge)why.push_back("interior ("+f(edge->second,1)+"mm > 0.6mm off the "+edge->first+" edge)");if(!mouth)why.push_back("mouth "+pair_repr(face)+" faces inward (off-board for the "+edge->first+" edge is "+pair_repr(outward.at(edge->first))+")");res.bad_connectors.push_back(inst.ref+" ("+inst.sheet+") "+part+": "+join(why,"; "));}
    }
    if(m.som_core)for(std::size_t i=0;i<m.insts.size();++i){const auto& inst=m.insts[i];auto b=input.courtyard_at(i);
        if(overlap_area(b,*m.som_core)<=0.5)continue;auto filename=std::filesystem::path(inst.mod->source).filename().string();
        if(starts(filename,"MountingHole")||starts(filename,"Fiducial")||starts(inst.sheet,"som_j")||inst.side=="bottom")continue;
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
bool pcb_is_df40_part(const std::string& sheet,int pins){static const std::regex rx("^som_j[0-9]+$");return pins>=40||std::regex_match(sheet,rx);}
bool pcb_counts_as_crowder(const std::string& ref,const std::string& sheet,int pins,const std::string& footprint,const std::string& subject_sheet){return !(pcb_is_df40_part(sheet,pins)||footprint.find("Fiducial")!=std::string::npos||is_testpoint_ref(ref)||(sheet==subject_sheet&&is_cluster_passive(ref,pins,{"RS","RJ","RN","LED"},{"R","C","L"})));}
std::pair<double,std::string> pcb_fanout_need(int pins){return intelligent_need(pins,{{2,0.2,"2-pin passive — escapes on its own pads"},{8,1.5,"<=8-pin non-passive — 1.5 mm absolute floor (user law 2026-07-29)"}},2,">=9-pin package — 2.0 mm floor (user law 2026-07-29)");}
PcbFanoutResult check_fanout(const PcbCheckInput& input,std::optional<int> baseline){
    const auto& m=input.model();PcbFanoutResult res;std::vector<Box4> boxes;
    // fanout_gate.check deliberately reads every courtyard before filtering.
    for(std::size_t i=0;i<m.insts.size();++i)boxes.push_back(input.courtyard_at(i));
    for(std::size_t i=0;i<m.insts.size();++i){const auto& inst=m.insts[i];int pins=static_cast<int>(inst.pad_nets.size());if(pcb_is_df40_part(inst.sheet,pins)||pins<3)continue;
        auto need=pcb_fanout_need(pins);std::vector<Box4> others;std::vector<std::size_t> indices;
        for(std::size_t j=0;j<m.insts.size();++j){const auto& o=m.insts[j];if(i!=j&&o.side==inst.side&&pcb_counts_as_crowder(o.ref,o.sheet,static_cast<int>(o.pad_nets.size()),o.footprint,inst.sheet)){others.push_back(boxes[j]);indices.push_back(j);}}
        auto best=nearest_rect_gap(boxes[i],others,1e-4);
        std::string ref="(none)",sheet="-";if(best.index>=0){const auto& o=m.insts[indices.at(static_cast<std::size_t>(best.index))];if(!o.ref.empty())ref=o.ref;if(!o.sheet.empty())sheet=o.sheet;}
        res.records.push_back({inst.ref,inst.sheet,inst.side,pins,best.gap,need.first,ref,sheet,need.second});
    }
    std::stable_sort(res.records.begin(),res.records.end(),[](const auto& a,const auto& b){return a.slack()==b.slack()?a.ref<b.ref:a.slack()<b.slack();});
    res.n_subjects=static_cast<int>(res.records.size());for(const auto& r:res.records)if(r.starved())++res.n_starved;res.baseline=baseline.value_or(res.n_starved);res.ok=res.n_starved<=*res.baseline;
    if(!res.ok)for(const auto& r:res.records)if(r.starved())res.regressions.push_back(r.ref+" ("+r.sheet+") "+std::to_string(r.pins)+"pin: clr="+f(r.clearance,3)+" < need="+f(r.need,2));return res;
}
int pcb_fanout_ratchet(int n,std::optional<int> previous){return previous?std::min(*previous,n):n;}
std::string PcbFanoutResult::summary()const{
    std::vector<std::string> l={"FAN-OUT CLEARANCE GATE (D13, report-first ratchet): "+verdict(ok),"  multi-pin subjects: "+std::to_string(n_subjects)+"  starved: "+std::to_string(n_starved)+"  baseline(ratchet): "+(baseline?std::to_string(*baseline):"unset"),"  intelligent need = pin-count tier; clearance = min courtyard gap to nearest FOREIGN part","  cluster-aware: own-sheet 2-pin R/C/L excluded; DF40 plugs (som_j*, >=40-pin) excluded (no-inflate)","  OFFENDERS (starved, worst slack first):"};
    bool any=false;for(const auto& r:records)if(r.starved()){any=true;l.push_back("    STARVED "+pad(r.ref,9)+" "+pad(r.sheet,16)+" "+pad(std::to_string(r.pins),3,true)+"pin ["+r.side.substr(0,3)+"] clr="+f(r.clearance,3)+" need="+f(r.need,2)+" slack="+sign(r.slack(),3)+" nearest="+r.nearest_ref+" ("+r.nearest_sheet+")");}if(!any)l.push_back("    (none)");
    if(!regressions.empty()){l.push_back("  RATCHET REGRESSION ("+std::to_string(regressions.size())+" — starved count "+std::to_string(n_starved)+" > baseline "+(baseline?std::to_string(*baseline):"None")+"):");for(const auto& s:regressions)l.push_back("    REGRESSION: "+s);}
    int count=0;for(const auto& r:records)if(!r.starved()&&count<5){if(count++==0)l.push_back("  (tightest PASSING subjects:)");l.push_back("    ok      "+pad(r.ref,9)+" "+pad(r.sheet,16)+" "+pad(std::to_string(r.pins),3,true)+"pin clr="+f(r.clearance,3)+" need="+f(r.need,2)+" slack="+sign(r.slack(),3));}return join(l);
}
} // namespace schgen
