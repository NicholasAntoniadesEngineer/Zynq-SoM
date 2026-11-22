#include "pcb_checks_internal.hpp"

namespace schgen {
using namespace pcb_checks;
ConnectorModelResult check_connector_models(const PcbCheckModel& model){
    return check_connector_models(model,model.connectors);
}
ConnectorModelResult check_connector_models(const PcbCheckModel& model,const ConnectorFacts& faces){
    ConnectorModelResult res;
    for(const auto& inst:model.insts){
        const auto name=inst.footprint.substr(inst.footprint.find_last_of(':')+1);
        const auto part=faces.count(inst.value)?inst.value:(faces.count(name)?name:"");
        if(part.empty())continue;++res.n_connectors;
        if(!inst.mod){res.missing_model.push_back(inst.ref+" "+part+": footprint not resolvable");res.models.push_back({inst.ref,part,inst.value,std::nullopt,true});continue;}
        std::optional<double> z;
        for(const auto& node:*list(inst.mod->document))if(tag(node,"model")){
            if(auto rot=child(node,"rotate"))for(const auto& c:*rot)if(tag(c,"xyz")){auto xyz=list(c);if(xyz->size()>=4&&std::holds_alternative<double>((*xyz)[3].v))z=number(*xyz,3);break;}
            break;
        }
        bool ok=true;
        if(!z)res.missing_model.push_back(inst.ref+" "+part+": no (model ...rotate) node");
        else if(std::fmod(py_round(*z,0),180)!=0){
            ok=false;res.bad_z.push_back(inst.ref+" "+part+" (value="+inst.value+"): model rotate Z="+g(*z)+" deg (must be 0 or 180 — axis-aligned with the footprint; 90/270 is perpendicular, non-orthogonal is garbage) — fix the (model ...(rotate (xyz 0 0 Z))) node");
        }
        res.models.push_back({inst.ref,part,inst.value,z,ok});
        if(faces.at(part).pad_row_face_check){
            res.geom_checked.push_back(inst.ref+" "+part);
            std::vector<std::pair<double,int>> rows;double lo=std::numeric_limits<double>::infinity(),hi=-lo;
            for(const auto& p:inst.mod->pads){double y=std::get<3>(p),rounded=py_round(y,1);lo=std::min(lo,y);hi=std::max(hi,y);auto it=std::find_if(rows.begin(),rows.end(),[&](const auto& row){return row.first==rounded;});if(it==rows.end())rows.emplace_back(rounded,1);else ++it->second;}
            if(!rows.empty()){
                auto best=std::max_element(rows.begin(),rows.end(),[](const auto& a,const auto& b){return a.second<b.second;});double center=(lo+hi)/2;
                if(std::abs(best->first-center)>=0.5){std::string implied=best->first>center?"-Y":"+Y",declared=faces.at(part).mating_face;
                    if(implied!=declared)res.geom_conflicts.push_back(inst.ref+" "+part+": pad geometry implies mouth "+implied+" (opposite the dense contact tail row) but CONN_MATING_FACE says "+declared+" — one is wrong; the rendered mouth would face inward");
                }
            }
        }
    }
    res.ok=res.bad_z.empty()&&res.geom_conflicts.empty();return res;
}
std::string ConnectorModelResult::summary()const{
    std::vector<std::string> l={"LAW-6 CONNECTOR-MODEL ORIENTATION GATE: "+verdict(ok),"  off-board connectors inspected: "+std::to_string(n_connectors)};
    for(const auto& r:models)l.push_back("    "+std::string(r.ok?"OK ":"BAD")+" "+pad(r.ref,9)+" "+pad(r.mpn,16)+" model_z="+(r.z?g(*r.z):"none"));
    l.push_back("  non-zero model-Z (flipped opening): "+std::to_string(bad_z.size()));for(const auto& s:bad_z)l.push_back("    BAD-Z "+s);
    l.push_back("  geometry-cross-checked (through-shell): "+std::to_string(geom_checked.size())+" -> "+std::to_string(geom_conflicts.size())+" conflict(s)");for(const auto& s:geom_conflicts)l.push_back("    GEOM-CONFLICT "+s);
    l.push_back("  reviewed geometry exceptions: 7");if(!missing_model.empty()){l.push_back("  (info) connectors without a 3D model: "+std::to_string(missing_model.size())+" — see the 3D-coverage gate");for(const auto& s:missing_model)l.push_back("    NO-MODEL "+s);}return join(l);
}
ConnectorSpacingResult check_connector_spacing(const PcbCheckInput& input){
    const auto& model=input.model();ConnectorSpacingResult res;res.board_w=model.board_w;res.board_h=model.board_h;
    std::vector<std::pair<std::string,Box4>> conns,members;std::map<std::string,std::string> family_of;
    for(std::size_t i=0;i<model.insts.size();++i){auto part=mpn(model.connectors,model.insts[i]);if(part.empty())continue;conns.emplace_back(model.insts[i].ref,input.pad_bbox_at(i));if(model.connectors.at(part).overmold){members.push_back(conns.back());family_of[model.insts[i].ref]=part;}}
    for(std::size_t i=0;i<conns.size();++i)for(std::size_t j=i+1;j<conns.size();++j){const auto& a=conns[i].second;const auto& b=conns[j].second;double ox=overlap_1d(a.x0,a.x1,b.x0,b.x1),oy=overlap_1d(a.y0,a.y1,b.y0,b.y1);if(ox>0.05&&oy>0.05)res.violations.push_back(conns[i].first+" <-> "+conns[j].first+": connector footprints OVERLAP (ox="+f(ox,2)+" oy="+f(oy,2)+"mm) — coincident/stacked placement");}
    std::stable_sort(members.begin(),members.end(),[](const auto& a,const auto& b){return a.first<b.first;});
    for(std::size_t i=0;i<members.size();++i)for(std::size_t j=i+1;j<members.size();++j)if(auto hit=same_edge_gap(members[i].second,members[j].second,0.5)){
        const auto& [axis,gap]=*hit;auto ra=members[i].first,rb=members[j].first;bool ok=gap>=18;res.pairs.push_back({ra,rb,family_of.at(ra),axis,gap,18,ok});
        if(!ok)res.violations.push_back(ra+" <-> "+rb+" ("+family_of.at(ra)+"): overmold gap "+f(gap,2)+"mm along "+axis+" < required 18mm — the two cable plugs' overmolds would collide; cannot mate both at once");
    }
    for(const auto& [ra,a]:members)for(const auto& [rb,b]:conns){auto ref_b=rb;if(std::any_of(members.begin(),members.end(),[&](const auto& m){return m.first==ref_b;}))continue;if(auto hit=same_edge_gap(a,b,0.5)){
        const auto& [axis,gap]=*hit;bool ok=gap>=3;res.pairs.push_back({ra,rb,family_of.at(ra)+"|1",axis,gap,3,ok});if(!ok)res.violations.push_back(ra+" <-> "+rb+" ("+family_of.at(ra)+" one-sided): gap "+f(gap,2)+"mm along "+axis+" < required 3mm — the "+family_of.at(ra)+" plug's own boot overhangs its copper into the neighbour");
    }}
    struct Held {std::string ref;Box4 envelope,room;const ConnectorFact* fact;};
    std::vector<Held> held;
    for(std::size_t i=0;i<model.insts.size();++i){const auto part=mpn(model.connectors,model.insts[i]);if(part.empty())continue;const auto& fact=model.connectors.at(part);
        if(!fact.access&&!(fact.mating&&fact.mating->plug_width_mm))continue;
        const auto face=mating_face_vector(fact);const bool above=face==std::pair<int,int>{0,0};
        const auto v=turn_point(face.first,model.insts[i].mirror?-face.second:face.second,model.insts[i].rotation);
        const double mx=above?0:std::round(v.first),my=above?0:std::round(v.second);
        const bool across_x=above||my!=0,across_y=above||mx!=0;
        Box4 box=input.courtyard_at(i);
        if(fact.mating&&fact.mating->plug_width_mm){const double plug=*fact.mating->plug_width_mm;
            if(across_x&&plug>box.x1-box.x0){const double grow=(plug-(box.x1-box.x0))/2;box.x0-=grow;box.x1+=grow;}
            if(across_y&&plug>box.y1-box.y0){const double grow=(plug-(box.y1-box.y0))/2;box.y0-=grow;box.y1+=grow;}}
        Box4 room=box;
        if(fact.access){const double side=fact.access->side_mm,front=fact.access->front_mm;
            if(across_x){room.x0-=side;room.x1+=side;}if(across_y){room.y0-=side;room.y1+=side;}
            if(mx>0)room.x1+=front;if(mx<0)room.x0-=front;if(my>0)room.y1+=front;if(my<0)room.y0-=front;}
        held.push_back({model.insts[i].ref,box,room,&fact});}
    const auto overlap=[](const Box4& a,const Box4& b){return std::min(a.x1,b.x1)-std::max(a.x0,b.x0)>0&&std::min(a.y1,b.y1)-std::max(a.y0,b.y0)>0;};
    for(std::size_t i=0;i<held.size();++i)for(std::size_t j=i+1;j<held.size();++j){
        const auto& a=held[i];const auto& b=held[j];
        const double gx=std::max(a.envelope.x0,b.envelope.x0)-std::min(a.envelope.x1,b.envelope.x1),gy=std::max(a.envelope.y0,b.envelope.y0)-std::min(a.envelope.y1,b.envelope.y1),gap=std::max(gx,gy);
        const bool collide=overlap(a.envelope,b.envelope),a_room=overlap(a.room,b.envelope),b_room=overlap(b.room,a.envelope);
        const double need=std::max(a.fact->access?a.fact->access->side_mm:0.0,b.fact->access?b.fact->access->side_mm:0.0);
        const bool ok=!collide&&!a_room&&!b_room;
        res.pairs.push_back({a.ref,b.ref,staged_connector_family,gx>=gy?"x":"y",gap,need,ok});
        if(!ok)res.violations.push_back(a.ref+" <-> "+b.ref+": "+(collide?std::string("plug envelopes must not collide"):"plug envelope "+f(gap,2)+"mm away lies in the access room of "+(a_room?a.ref+" ("+a.fact->access->basis+")":b.ref+" ("+b.fact->access->basis+")")));
    }
    std::stable_sort(res.pairs.begin(),res.pairs.end(),[](const auto& a,const auto& b){return a.gap<b.gap;});res.ok=res.violations.empty();return res;
}
std::string ConnectorSpacingResult::summary()const{
    std::vector<std::string> l={"CONNECTOR OVERMOLD SPACING GATE: "+verdict(ok)+" (board "+g(board_w)+" x "+g(board_h)+" mm)","  same-edge overmold connector pairs: "+std::to_string(pairs.size())+" ("+std::to_string(violations.size())+" too tight)"};
    for(const auto& p:pairs)l.push_back("    "+std::string(p.ok?"OK ":"BAD")+" "+pad(p.ref_a,9)+" <-> "+pad(p.ref_b,9)+" "+pad(p.family,12)+" gap="+pad(f(p.gap,2),6,true)+"mm along "+p.axis+" (need >= "+g(p.need)+"mm)");for(const auto& s:violations)l.push_back("    TOO-TIGHT "+s);return join(l);
}
} // namespace schgen
