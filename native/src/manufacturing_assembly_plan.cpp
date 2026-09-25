#include "manufacturing_assembly_internal.hpp"
#include "schgen/turn.hpp"

namespace schgen {
using namespace assembly_detail;
namespace {
std::vector<std::string> polarity(const PcbModel& m,const Indices& ids) {
    std::vector<std::string> d,u,cp,out;
    for(auto n:ids){const auto& i=m.insts.at(n);if(starts(i.ref,"D"))d.push_back(i.ref);if(starts(i.ref,"U")||starts(i.ref,"Q"))u.push_back(i.ref);if(has(i.footprint,":CP_"))cp.push_back(i.ref);}
    sort_refs(d);sort_refs(u);sort_refs(cp);
    if(!d.empty())out.push_back("diode polarity ("+(d.size()<=8?join(d,", "):std::to_string(d.size())+" parts, D refs")+"): cathode per silkscreen");
    if(!cp.empty())out.push_back("electrolytic polarity ("+join(cp,", ")+"): positive mark per silkscreen");
    if(!u.empty())out.push_back("pin-1 orientation ("+(u.size()<=8?join(u,", "):std::to_string(u.size())+" parts, U/Q refs")+"): dot per silkscreen");
    return out;
}
std::string description(const PcbCheckInstance& i,const PcbEmitPolicy& p) {
    for(const auto& [k,v]:p.header_descriptions)if(k==i.ref)return v;
    return lookup(p.connector_descriptions,i.sheet);
}
std::vector<std::string> connector_notes(const PcbModel& m,Indices ids,const PcbEmitPolicy& p) {
    sort_indices(ids,m);std::vector<std::string> out,som;Indices xt;
    for(auto n:ids){const auto& i=m.insts.at(n);const auto face=lookup(p.connector_mating_faces,stem(i));
        if(starts(i.sheet,"som_j"))som.push_back(i.ref);
        if(stem(i)=="XT60PW-M")xt.push_back(n);
        if(face.empty())continue;
        const auto v=turn_point(face=="+X"?1:face=="-X"?-1:0,face=="+Y"?1:face=="-Y"?-1:0,i.rotation);
        const auto x=rounded(v.first),y=rounded(v.second);
        std::string edge;if(x==0&&y==-1)edge="N";else if(x==0&&y==1)edge="S";else if(x==1&&y==0)edge="E";else if(x==-1&&y==0)edge="W";else throw ProjectError(i.ref+": non-cardinal connector mating face");
        auto desc=description(i,p);out.push_back(i.ref+" "+i.value+(desc.empty()?"":" ("+desc+")")+": mating face toward the "+edge+" board edge");
    }
    if(xt.size()==2){const auto& a=m.insts[xt[0]];const auto& b=m.insts[xt[1]];out.push_back("XT60 pair: "+a.ref+" ("+description(a,p)+") / "+b.ref+" ("+description(b,p)+") — IN/OUT per silkscreen label");}
    if(!som.empty())out.push_back(join(som,", ")+": DF40C SoM receptacles — the SoM module mates onto them (bring-up section, mate phase)");
    return out;
}
struct Rails {
    std::map<std::string,std::string> parent;
    std::map<std::string,std::vector<const PowerReg*>> producers;
    std::map<std::string,int> depth;
    std::string group(std::string n)const { while(parent.count(n)&&parent.at(n)!=n)n=parent.at(n);return n; }
    int rank(const std::string& n)const {auto p=depth.find(group(n));return p==depth.end()?0:p->second;}
    explicit Rails(const PowerCheckResult& p){
        for(const auto& b:p.bridges){auto a=group(b.from),c=group(b.to);if(a!=c)parent[std::max(a,c)]=std::min(a,c);}
        Names groups;for(const auto& r:p.regs){producers[group(r.vout)].push_back(&r);groups.insert(group(r.vin));groups.insert(group(r.vout));}
        for(const auto& g:groups)if(!producers.count(g))depth[g]=0;
        for(std::size_t n=0;n<=groups.size();++n)for(const auto& r:p.regs){auto a=group(r.vin),b=group(r.vout);if(depth.count(a)&&(!depth.count(b)||depth[b]>depth[a]+1))depth[b]=depth[a]+1;}
    }
};
void append(Names& a,const Names& b) {a.insert(b.begin(),b.end());}
}
std::string assembly_joint(const PcbCheckFootprint& fp) {
    static const std::regex re(R"re(\(pad\s+"[^"]*"\s+(\w+))re");std::size_t smd=0,tht=0;
    for(std::sregex_iterator i(fp.bytes.begin(),fp.bytes.end(),re),end;i!=end;++i){const auto t=(*i)[1].str();smd+=t=="smd";tht+=t=="thru_hole";}
    return tht>smd?"tht":"smd";
}
std::vector<AssemblyStep> assembly_process_steps(const PcbModel& m,const PcbEmitPolicy& p) {
    std::vector<AssemblyStep> out{{1,"bottom_smd","Bottom-side SMD (paste + reflow)",{},{}},{2,"top_smd","Top-side SMD (paste + reflow)",{},{}},{3,"tht","Through-hole (short-to-tall)",{},{}},{4,"connectors_mech","Connectors + mechanical hardware",{},{}}};
    for(auto n:parts(m)){const auto& i=m.insts[n];std::size_t g=connector(i)||mechanical(i)?3:assembly_joint(footprint(i))=="tht"?2:i.side=="bottom"?0:1;out[g].insts.push_back(n);}
    for(auto& s:out){sort_indices(s.insts,m);s.notes=s.n==4?connector_notes(m,s.insts,p):polarity(m,s.insts);}
    auto area=[&](auto n){auto b=footprint(m.insts[n]).bbox;if(!b)throw ProjectError(m.insts[n].ref+": footprint has no measurable extent");return decimal_round((b->x1-b->x0)*(b->y1-b->y0),3);};
    std::stable_sort(out[2].insts.begin(),out[2].insts.end(),[&](auto a,auto b){return area(a)<area(b);});
    partition(m,out,"step");return out;
}
std::vector<AssemblyPhase> assembly_bringup_phases(const PcbModel& m,const PowerCheckResult& power,const PcbEmitPolicy& policy) {
    Rails rails(power);PcbCheckInput geometry(m);std::map<std::string,Indices> by_sheet;
    std::map<std::string,Names> touched,produced,roots;Names universe,all_produced;
    for(auto n:parts(m))by_sheet[m.insts[n].sheet].push_back(n);
    for(const auto& [n,c]:m.netclass_of)if(c=="POWER")universe.insert(n);
    for(const auto& r:power.regs){produced[r.sheet].insert(r.vout);all_produced.insert(r.vout);}
    for(const auto& i:m.insts){auto& nets=touched[i.sheet];for(const auto& [pad,net]:i.pad_nets){(void)pad;if(universe.count(net.second))nets.insert(net.second);}
    }
    // Connector roots use only each connector's own pads, never all sheet pads.
    for(const auto& i:m.insts)if(!lookup(policy.connector_mating_faces,stem(i)).empty())for(const auto& [pad,net]:i.pad_nets){(void)pad;if(universe.count(net.second)&&!all_produced.count(net.second))roots[i.sheet].insert(net.second);}
    Indices ordered;for(std::size_t n=0;n<m.insts.size();++n)ordered.push_back(n);sort_indices(ordered,m);
    std::map<std::string,std::string> tp;
    for(auto n:ordered){const auto& i=m.insts[n];if(!starts(i.ref,"TP"))continue;std::vector<std::pair<int,std::string>> nets;for(const auto& [pad,v]:i.pad_nets){(void)pad;nets.push_back(v);}std::sort(nets.begin(),nets.end());for(const auto& v:nets)if(!v.second.empty())tp.emplace(v.second,i.ref);}
    std::vector<std::string> modules,entries,chain,mech,rest;Names module_rails;
    for(const auto& [s,ids]:by_sheet)if(m.som_keepout&&std::all_of(ids.begin(),ids.end(),[&](auto n){auto b=geometry.courtyard_at(n),k=*m.som_keepout;auto x=(b.x0+b.x1)/2,y=(b.y0+b.y1)/2;return k.x0<=x&&x<=k.x1&&k.y0<=y&&y<=k.y1;})){modules.push_back(s);append(module_rails,touched[s]);}
    Names closure;std::vector<std::string> todo;for(const auto& r:module_rails)todo.push_back(rails.group(r));
    while(!todo.empty()){auto g=todo.back();todo.pop_back();if(!closure.insert(g).second)continue;for(auto r:rails.producers[g])todo.push_back(rails.group(r->vin));}
    Names entry_roots,conn_groups;for(const auto& [s,rs]:roots){(void)s;for(const auto& r:rs)conn_groups.insert(rails.group(r));}
    for(const auto& g:closure)if(rails.producers[g].empty()&&conn_groups.count(g))entry_roots.insert(g);
    for(const auto& [s,rs]:touched)if(!contains(modules,s)&&std::any_of(rs.begin(),rs.end(),[&](const auto& r){return entry_roots.count(rails.group(r));}))entries.push_back(s);
    std::vector<std::pair<double,std::string>> ranked;
    for(const auto& [s,ids]:by_sheet){(void)ids;if(contains(modules,s)||contains(entries,s))continue;std::vector<double> ranks;
        for(const auto& r:produced[s])if(closure.count(rails.group(r)))ranks.push_back(rails.rank(r));
        for(const auto& b:power.bridges)if(b.sheet==s&&closure.count(rails.group(b.from)))ranks.push_back(rails.rank(b.from)+.5);
        if(!ranks.empty())ranked.emplace_back(*std::min_element(ranks.begin(),ranks.end()),s);
    }
    std::sort(ranked.begin(),ranked.end());for(const auto& [rank,s]:ranked){(void)rank;chain.push_back(s);}
    for(const auto& [s,ids]:by_sheet)if(!contains(modules,s)&&!contains(entries,s)&&!contains(chain,s)){
        if(std::all_of(ids.begin(),ids.end(),[&](auto n){return mechanical(m.insts[n]);}))mech.push_back(s);else rest.push_back(s);
    }
    std::map<std::string,std::size_t> ranks;auto produces=produced;for(const auto& s:rest){append(produces[s],roots[s]);ranks[s]=0;}
    for(std::size_t it=0;it<rest.size();++it)for(const auto& a:rest)for(const auto& b:rest)if(a!=b&&std::any_of(produces[a].begin(),produces[a].end(),[&](const auto& n){return touched[b].count(n);})&&ranks[b]<ranks[a]+1&&ranks[a]+1<rest.size())ranks[b]=ranks[a]+1;
    std::stable_sort(rest.begin(),rest.end(),[&](const auto& a,const auto& b){return ranks[a]<ranks[b];});
    std::vector<AssemblyPhase> out;
    const auto add=[&](const std::string& slug,const std::string& title,const std::vector<std::string>& group,const Names& rs){
        AssemblyPhase phase;phase.n=static_cast<int>(out.size()+1);phase.slug=slug;phase.title=title;phase.sheets=group;
        for(const auto& s:group)phase.insts.insert(phase.insts.end(),by_sheet[s].begin(),by_sheet[s].end());sort_indices(phase.insts,m);
        Names expanded;for(const auto& r:rs){auto all=universe;all.insert(r);for(const auto& n:all)if(rails.group(n)==rails.group(r))expanded.insert(n);}
        std::vector<std::tuple<int,std::string,std::string>> hits;for(const auto& r:expanded)if(tp.count(r))hits.emplace_back(rails.rank(r),r,tp[r]);std::sort(hits.begin(),hits.end());
        for(const auto& [rank,r,t]:hits){(void)rank;phase.checkpoints.push_back("verify "+r+" at "+t);}out.push_back(std::move(phase));
    };
    if(!entries.empty()){Names rs;for(const auto& s:entries){for(const auto& r:touched[s])if(entry_roots.count(rails.group(r)))rs.insert(r);append(rs,produced[s]);}add("power_entry","power entry ("+join(entries,", ")+")",entries,rs);}
    for(const auto& s:chain)add(s,s,{s},produced[s]);
    if(!modules.empty()){
        add("som_interface","SoM interface ("+join(modules,", ")+")",modules,{});std::vector<std::string> recs,checkpoints;
        for(const auto& s:modules)for(auto n:by_sheet[s])if(connector(m.insts[n]))recs.push_back(m.insts[n].ref);sort_refs(recs);
        if(by_sheet.count("debug_boot")){auto ids=by_sheet["debug_boot"];sort_indices(ids,m);std::vector<std::string> debug;
            for(auto n:ids){const auto& i=m.insts[n];if(!starts(i.ref,"J")&&!starts(i.ref,"S"))continue;auto d=lookup(policy.header_descriptions,i.ref);if(d.empty())d=lookup(policy.switch_descriptions,i.ref);debug.push_back(i.ref+(d.empty()?"":" ("+d+")"));}checkpoints.push_back("boot/debug via debug_boot: "+join(debug,", "));}
        out.push_back({static_cast<int>(out.size()+1),"som_mate","SoM module mate",{},{},checkpoints,"No solder parts. Mate the SoM module onto "+join(recs,", ")+" after the rail checkpoints above."});
    }
    for(const auto& s:rest){auto rs=produced[s];append(rs,roots[s]);add(s,s,{s},rs);}
    for(const auto& s:mech)add(s,"mechanical hardware ("+s+")",{s},{});
    partition(m,out,"phase");return out;
}
AssemblyPlan assembly_plan(const PcbModel& m,const PowerCheckResult& p,const PcbEmitPolicy& policy) {return {assembly_process_steps(m,policy),assembly_bringup_phases(m,p,policy)};}
} // namespace schgen
