#include "pcb_checks_internal.hpp"
#include <numeric>

namespace schgen {
using namespace pcb_checks;
namespace {
Box4 segment_box(const PcbCheckCopper& s,bool width=true){double r=width?s.width/2:0;return {std::min(s.x1,s.x2)-r,std::min(s.y1,s.y2)-r,std::max(s.x1,s.x2)+r,std::max(s.y1,s.y2)+r};}
Box4 via_box(const PcbCheckCopper& v){return {v.x-v.size/2,v.y-v.size/2,v.x+v.size/2,v.y+v.size/2};}
std::string position(const PcbCheckCopper& c){return "("+pyfloat(c.x)+","+pyfloat(c.y)+")";}
void network(const PcbCheckInput& input,const std::map<std::string,std::size_t>& conns,const std::vector<const PcbCheckCopper*>& vias,const std::vector<const PcbCheckCopper*>& segs,ReturnStitchResult& res){
    const auto& m=input.model();auto fail=[&](std::string s){res.ok=false;res.violations.push_back(std::move(s));};
    Box4 plane{m.origin_x+0.5,m.origin_y+0.5,m.origin_x+m.board_w-0.5,m.origin_y+m.board_h-0.5};std::vector<std::pair<Box4,std::string>> voids;
    for(std::size_t i=0;i<m.insts.size();++i)if(starts(m.insts[i].value,"HX5008")||starts(m.insts[i].value,"KH-5224")){auto b=input.courtyard_at(i);voids.push_back({{b.x0-0.6,b.y0-0.6,b.x1+0.6,b.y1+0.6},"ethernet_isolation_void_"+m.insts[i].ref});}
    struct Group{std::vector<const PcbCheckCopper*> vias,segs;};std::map<std::string,Group> groups;for(auto v:vias)groups[v->conn].vias.push_back(v);for(auto s:segs)groups[s->conn].segs.push_back(s);
    for(const auto& [ref,group]:groups){auto index=conns.at(ref);const auto& inst=m.insts[index];std::vector<Box4> nodes;for(auto v:group.vias)nodes.push_back(via_box(*v));for(auto s:group.segs)nodes.push_back(segment_box(*s));std::size_t ncu=nodes.size();for(const auto& [pad,box]:input.geometry_at(index).pad_boxes)if(net_name(inst,pad)=="GND")nodes.push_back(box);
        std::vector<std::size_t> parent(nodes.size());std::iota(parent.begin(),parent.end(),0);auto find=[&](std::size_t i){while(parent[i]!=i){parent[i]=parent[parent[i]];i=parent[i];}return i;};
        for(std::size_t i=0;i<nodes.size();++i)for(std::size_t j=i+1;j<nodes.size();++j)if((i<ncu||j<ncu)&&touches(nodes[i],nodes[j]))parent[find(i)]=find(j);
        std::set<std::size_t> roots;for(std::size_t i=0;i<ncu;++i)roots.insert(find(i));if(roots.size()!=1)fail(ref+": ladder+vias form "+std::to_string(roots.size())+" components (expected ONE GND-only component)");
        for(auto v:group.vias){if(std::none_of(group.segs.begin(),group.segs.end(),[&](auto s){return touches(via_box(*v),segment_box(*s));}))fail(ref+": via at "+position(*v)+" touches no F.Cu ladder copper (fill-dependent connectivity — LAW 0)");if(!contains(plane,v->x,v->y))fail(ref+": via at "+position(*v)+" outside the canonical In1 GND plane "+box_repr(plane));for(const auto& [b,label]:voids)if(contains(b,v->x,v->y))fail(ref+": via at "+position(*v)+" inside In1 plane VOID "+label+" — no plane to land on");}
        int stubs=0;for(auto s:group.segs)if(starts(s->role,"stub")&&s->role!="stub_via")++stubs;if(stubs<2)fail(ref+": "+std::to_string(stubs)+" GND-pad stub(s) < 2");
    }
}
void clearance(const PcbCheckInput& input,const std::vector<const PcbCheckCopper*>& vias,const std::vector<const PcbCheckCopper*>& segs,ReturnStitchResult& res){
    if(vias.empty()&&segs.empty())return;const auto& m=input.model();auto fail=[&](std::string s){res.ok=false;res.violations.push_back(std::move(s));};
    double inf=std::numeric_limits<double>::infinity();Box4 win{inf,inf,-inf,-inf};auto add=[&](double x,double y){win=united(win,{x,y,x,y});};for(auto v:vias)add(v->x,v->y);for(auto s:segs){add(s->x1,s->y1);add(s->x2,s->y2);}win={win.x0-3,win.y0-3,win.x1+3,win.y1+3};
    struct Foreign{Box4 box;std::string side;double rule;std::string label;};std::vector<Foreign> foreign;std::vector<std::size_t> order(m.insts.size());std::iota(order.begin(),order.end(),0);std::stable_sort(order.begin(),order.end(),[&](auto a,auto b){return m.insts[a].ref<m.insts[b].ref;});
    for(auto i:order){const auto& inst=m.insts[i];for(const auto& [pad,b]:input.geometry_at(i).pad_boxes){auto net=net_name(inst,pad);if(net=="GND")continue;auto cls=m.netclass_of.find(net);double rule=cls!=m.netclass_of.end()&&cls->second=="POWER"?0.2:0.15;if(b.x1<win.x0||b.x0>win.x1||b.y1<win.y0||b.y0>win.y1)continue;foreign.push_back({b,inst.side,rule,inst.ref+"."+pad});}}
    for(auto v:vias)for(const auto& o:foreign){double d=point_box_dist(v->x,v->y,o.box);if(d<v->size/2+o.rule)fail("via "+position(*v)+" vs foreign "+o.label+": "+f(d,4)+" < "+f(v->size/2+o.rule,4));}
    for(auto s:segs)for(const auto& o:foreign)if(o.side=="top"){double d=box_gap(segment_box(*s,false),o.box);if(d<s->width/2+o.rule)fail("segment "+s->role+" vs foreign "+o.label+": "+f(d,4)+" < "+f(s->width/2+o.rule,4));}
}
}
ReturnStitchResult check_return_stitch(const PcbCheckInput& input,const ReturnPathResult& v1,const std::map<std::string,ReturnStitchClass>& triage,std::string_view interface_bytes,const PcbEmittedBoard* emitted){
    ReturnStitchResult res;const auto& m=input.model();auto fail=[&](std::string s){res.ok=false;res.violations.push_back(std::move(s));};res.v1_verdict=v1.summary();
    if(v1.n_pairs!=69||v1.n_pair_contacts!=138||v1.n_fail()!=29||v1.worst_distance!=std::optional<int>(4))fail("v1 population drift: live {'n_pairs': "+std::to_string(v1.n_pairs)+", 'n_pair_contacts': "+std::to_string(v1.n_pair_contacts)+", 'n_fail': "+std::to_string(v1.n_fail())+", 'worst_distance': "+(v1.worst_distance?std::to_string(*v1.worst_distance):"None")+"} != pinned {'n_pairs': 69, 'n_pair_contacts': 138, 'n_fail': 29, 'worst_distance': 4} — the SoM interface moved; re-derive the stitching deliberately (update the pin in the same reviewed unit)");
    auto conns=connectors(m);if(conns.size()!=3||!conns.count("J1")||!conns.count("J2")||!conns.count("J3")){std::vector<std::string> refs;for(const auto& c:conns)refs.push_back(c.first);fail("DF40 receptacles missing: found "+list_repr(refs));return res;}
    std::vector<PcbCheckCopper> escape;std::vector<const PcbCheckCopper*> vias,segs;
    for(const auto& c:m.copper)if(c.group=="som_escape"){escape.push_back(c);if(c.kind=="via")vias.push_back(&c);if(c.kind=="segment")segs.push_back(&c);}
    res.n_vias=static_cast<int>(vias.size());auto gnd=m.net_numbers.find("GND");for(const auto& c:escape)if(gnd==m.net_numbers.end()||c.net!=gnd->second||c.net_name!="GND")fail("som_escape "+c.kind+" carries net "+std::to_string(c.net)+"/"+repr(c.net_name)+", expected "+(gnd==m.net_numbers.end()?"None":std::to_string(gnd->second))+"/'GND' (LAW 0)");
    res.n_contacts=v1.n_fail();for(const auto& r:{"J1","J2","J3"})res.per_conn[r]={0,0};
    for(const auto& v:v1.violations){auto index=conns.at(v.ref);auto it=input.geometry_at(index).pad_boxes.find(v.pad);if(it==input.geometry_at(index).pad_boxes.end()){fail(v.ref+" pad "+v.pad+": no pad box");continue;}auto b=it->second;double x=(b.x0+b.x1)/2,y=(b.y0+b.y1)/2;std::optional<double> best;
        for(auto via:vias){double d=std::hypot(via->x-x,via->y-y);best=best?std::min(*best,d):d;}
        auto cls=triage.find(v.net);if(cls==triage.end())throw std::runtime_error("return-stitch: uncurated DF40 signal net "+repr(v.net));const auto& c=cls->second;res.coverage.push_back({c.rank,c.klass,v.ref,v.pad,c.function,best});++res.per_conn[v.ref].first;
        if(!best||*best>2){++res.per_conn[v.ref].second;fail(v.ref+" pad "+v.pad+" ("+c.function+", "+c.klass+"): nearest som_escape GND via "+(best?f(*best,4)+" mm":"absent")+" > bound 2.0");}else{++res.n_covered;res.worst_mm=std::max(res.worst_mm,*best);}
    }
    if(!vias.empty()||!segs.empty())network(input,conns,vias,segs,res);clearance(input,vias,segs,res);
    if(m.escape_interface_sha256){res.hash_ok=*m.escape_interface_sha256==pcb_sha256(interface_bytes);if(!res.hash_ok)fail("escape_meta som_interface sha256 is STALE vs the live contract");}
    if(emitted){res.file_parity=pcb_escape_file_parity(*emitted,escape);if(res.file_parity!="ok")fail("file parity: "+res.file_parity);}return res;
}
std::string pcb_escape_file_parity(const PcbEmittedBoard& pcb,const std::vector<PcbCheckCopper>& escape){
    if(!pcb.exists)return "board file missing: "+pcb.source;if(!tag(pcb.document,"kicad_pcb"))throw std::runtime_error("PCB emitted board root required");
    const auto name=std::filesystem::path(pcb.source).filename().string();auto eq=[](double a,double b){return a==py_round(b,4);};
    for(const auto& c:escape){bool found=false;if(c.kind=="via"){
        for(const auto& node:*list(pcb.document))if(tag(node,"via")){auto a=child(node,"at"),s=child(node,"size"),d=child(node,"drill");if(a&&s&&d&&eq(number(*a,1),c.x)&&eq(number(*a,2),c.y)&&eq(number(*s,1),c.size)&&eq(number(*d,1),c.drill)){found=true;break;}}
        if(!found)return "via at "+position(c)+" absent from "+name;
    }else if(c.kind=="segment"){
        for(const auto& node:*list(pcb.document))if(tag(node,"segment")){auto a=child(node,"start"),b=child(node,"end");if(a&&b&&eq(number(*a,1),c.x1)&&eq(number(*a,2),c.y1)&&eq(number(*b,1),c.x2)&&eq(number(*b,2),c.y2)){found=true;break;}}
        if(!found)return "segment ("+pyfloat(c.x1)+","+pyfloat(c.y1)+")-("+pyfloat(c.x2)+","+pyfloat(c.y2)+") absent from "+name;
    }}
    for(const auto& node:*list(pcb.document))if(tag(node,"zone")){auto n=child(node,"name");if(n&&n->size()>1&&atom((*n)[1])=="GND_plane_In1")return "ok";}return "canonical GND_plane_In1 zone absent from "+name;
}
std::string ReturnStitchResult::summary()const{
    std::vector<std::string> l={"RETURN-STITCH GATE (return-path v2): "+verdict(ok)+" (radius "+pyfloat(radius)+" mm, HARD, class-blind)","  remediation set (v1-failing contacts): "+std::to_string(n_contacts),"  covered by som_escape GND vias        : "+std::to_string(n_covered),"  worst contact->via distance           : "+f(worst_mm,4)+" mm","  som_escape stitch vias                : "+std::to_string(n_vias),"  som_interface hash                    : "+std::string(hash_ok?"ok":"STALE"),"  emitted-file parity                   : "+file_parity,"  per-connector (contacts, uncovered):"};
    for(const auto& [ref,n]:per_conn)l.push_back("    "+ref+": "+std::to_string(n.first)+" contacts, "+std::to_string(n.second)+" uncovered");l.push_back("  triage-ranked coverage (GENUINE first — ordering only, never a waiver):");auto sorted=coverage;std::sort(sorted.begin(),sorted.end(),[](const auto& a,const auto& b){return std::tie(a.rank,a.klass,a.ref,a.pad,a.function,a.distance)<std::tie(b.rank,b.klass,b.ref,b.pad,b.function,b.distance);});
    for(const auto& c:sorted)l.push_back("    ["+pad(c.klass,8)+"] "+c.ref+" pad "+pad(c.pad,3,true)+" "+pad(c.function,28)+" -> "+(c.distance?f(*c.distance,4)+" mm":"NONE"));if(!violations.empty()){l.push_back("  VIOLATIONS:");for(const auto& v:violations)l.push_back("    "+v);}l.push_back("");l.push_back("  ---- return-path v1 verdict (SoM-design fact, quoted verbatim; NOT waived by this gate) ----");std::istringstream in(v1_verdict);std::string line;while(std::getline(in,line))l.push_back("  | "+line);return join(l);
}
} // namespace schgen
