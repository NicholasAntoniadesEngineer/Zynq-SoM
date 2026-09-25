#include "pcb_checks_internal.hpp"

namespace schgen {
using namespace pcb_checks;
std::string pcb_classify_net(const std::string& net){std::string up=net;for(char& c:up)if(c>='a'&&c<='z')c=char(c-'a'+'A');if(ends(up,"GND"))return "GND";if(starts(net,"+")||starts(up,"VCC")||starts(up,"VDD"))return "POWER";return "SIGNAL";}
namespace {
std::vector<std::string> tokens(const std::string& s){std::vector<std::string> out;std::size_t p=0;for(;;){auto q=s.find('_',p);out.push_back(s.substr(p,q==s.npos?q:q-p));if(q==s.npos)return out;p=q+1;}}
std::optional<int> within_distance(const ReturnPathContact& c,const std::vector<ReturnPathContact>& contacts,int k){
    std::map<int,const ReturnPathContact*> same;std::map<int,double> rows;
    for(const auto& x:contacts)if(x.row==c.row)same[x.index]=&x;else rows.emplace(x.row,x.y);
    std::optional<int> facing_row,best;double ydist=std::numeric_limits<double>::infinity();
    for(const auto& [row,y]:rows)if(std::abs(c.y-y)<ydist){ydist=std::abs(c.y-y);facing_row=row;}
    auto save=[&](int d){best=best?std::min(*best,d):d;};
    for(int di=-k;di<=k;++di){auto it=same.find(c.index+di);if(di!=0&&it!=same.end()&&it->second->klass=="GND")save(std::abs(di));}
    for(int di=-k;di<=k;++di){auto anchor=same.find(c.index+di);double ax=anchor==same.end()?c.x:anchor->second->x;const ReturnPathContact* closest=nullptr;double dx=std::numeric_limits<double>::infinity();
        if(facing_row)for(const auto& x:contacts)if(x.row==*facing_row&&std::abs(x.x-ax)<dx){dx=std::abs(x.x-ax);closest=&x;}
        if(closest&&closest->klass=="GND")save(std::max(1,std::abs(di)));
    }
    return best;
}
std::optional<int> any_distance(const ReturnPathContact& c,const std::vector<ReturnPathContact>& contacts){std::optional<int> best;for(const auto& x:contacts)if(x.klass=="GND"){int d=std::abs(x.index-c.index);if(x.row!=c.row)d=std::max(1,d);best=best?std::min(*best,d):d;}return best;}
}
std::optional<std::string> pcb_pair_partner(const std::string& net){auto ts=tokens(net);int count=0;for(auto& t:ts)if(t=="P"||t=="N"){++count;t=t=="P"?"N":"P";}if(count!=1)return std::nullopt;return join(ts,"_");}
std::string pcb_pair_base(const std::string& net,const std::string& partner){auto a=tokens(net),b=tokens(partner);a.resize(std::min(a.size(),b.size()));for(std::size_t i=0;i<a.size();++i)if(a[i]!=b[i])a[i]="*";return join(a,"_");}
std::map<std::string,std::string> pcb_hs_pairs(const std::set<std::string>& nets){std::map<std::string,std::string> out;for(const auto& n:nets)if(auto p=pcb_pair_partner(n))if(nets.count(*p))out[n]=pcb_pair_base(n,*p);return out;}
std::vector<ReturnPathContact> build_return_path_contacts(const std::string& ref,const XdcStrings& pins,const PcbCheckFootprint& fp){
    std::map<std::string,std::pair<double,double>> positions;for(const auto& p:fp.pads)if(!std::get<0>(p).empty())positions[std::get<0>(p)]={std::get<2>(p),std::get<3>(p)};
    return build_return_path_contacts(ref,pins,positions);
}
std::vector<ReturnPathContact> build_return_path_contacts(const std::string& ref,const XdcStrings& pins,const std::map<std::string,std::pair<double,double>>& positions){
    std::set<double,std::greater<double>> ys;for(const auto& [pad,p]:positions){(void)pad;ys.insert(p.second);}std::vector<double> row_y;
    for(double y:ys)if(std::none_of(row_y.begin(),row_y.end(),[&](double r){return std::abs(y-r)<=0.05;}))row_y.push_back(y);
    std::map<int,std::vector<std::pair<double,std::string>>> rows;for(const auto& [pad,p]:positions){double py=p.second;auto it=std::find_if(row_y.begin(),row_y.end(),[&](double y){return std::abs(y-py)<=0.05;});rows[static_cast<int>(it-row_y.begin())].emplace_back(p.first,pad);}
    std::map<std::string,std::pair<int,int>> address;for(auto& [r,entries]:rows){std::sort(entries.begin(),entries.end());for(std::size_t i=0;i<entries.size();++i)address[entries[i].second]={r,static_cast<int>(i)};}
    std::vector<ReturnPathContact> contacts;for(const auto& [pad,net]:pins){auto pos=positions.find(pad);if(pos==positions.end())continue;auto [r,i]=address.at(pad);contacts.push_back({ref,pad,r,i,pos->second.first,pos->second.second,net,pcb_classify_net(net)});}
    std::stable_sort(contacts.begin(),contacts.end(),[](const auto& a,const auto& b){return std::tie(a.row,a.index)<std::tie(b.row,b.index);});return contacts;
}
ReturnPathResult check_return_path(const std::map<std::string,std::vector<ReturnPathContact>>& by_ref,int k){
    if(k<0)throw std::runtime_error("return-path K must be nonnegative");ReturnPathResult res;res.k=k;std::set<std::string> all_bases;
    for(const auto& [ref,raw]:by_ref){res.connectors.push_back(ref);std::set<std::string> nets,bases;for(const auto& c:raw)nets.insert(c.net);auto pairs=pcb_hs_pairs(nets);for(const auto& [net,base]:pairs){(void)net;bases.insert(base);all_bases.insert(base);}
        auto contacts=raw;std::stable_sort(contacts.begin(),contacts.end(),[](const auto& a,const auto& b){return std::tie(a.row,a.index)<std::tie(b.row,b.index);});int pc=0,fc=0;
        for(const auto& c:contacts){auto pair=pairs.find(c.net);if(pair==pairs.end())continue;++pc;++res.n_pair_contacts;auto within=within_distance(c,raw,k),dist=within?within:any_distance(c,raw);
            if(dist){++res.dist_hist[*dist];res.worst_distance=res.worst_distance?std::max(*res.worst_distance,*dist):*dist;}
            if(!within){++fc;res.violations.push_back({ref,pair->second,c.net,c.pad,dist});}
        }res.per_conn[ref]={pc,fc};res.pairs_per_conn[ref]=static_cast<int>(bases.size());
    }
    res.n_pairs=static_cast<int>(all_bases.size());std::sort(res.violations.begin(),res.violations.end(),[](const auto& a,const auto& b){return std::tie(a.ref,a.base,a.net,a.pad)<std::tie(b.ref,b.base,b.net,b.pad);});res.ok=res.violations.empty();return res;
}
ReturnPathResult check_return_path(const SomInterface& iface,const std::map<std::string,PcbCheckFootprintPtr>& footprints,int k){
    std::map<std::string,std::vector<ReturnPathContact>> contacts;for(const auto& [ref,c]:iface.connectors){auto it=footprints.find(ref);if(it==footprints.end()||!it->second)throw std::runtime_error(ref+": cannot resolve footprint dossier (value="+(c.value?repr(*c.value):"None")+", footprint="+(c.footprint?repr(*c.footprint):"None")+")");contacts[ref]=build_return_path_contacts(ref,c.pins,*it->second);}return check_return_path(contacts,k);
}
std::string ReturnPathViolation::as_line()const{return ref+" pad "+pad+" net "+net+" (pair "+base+"): nearest GND at "+(distance?std::to_string(*distance):"none-on-connector")+" steps > K=2";}
std::string ReturnPathResult::summary()const{
    std::vector<std::string> l={"RETURN-PATH GATE (HS pairs): "+verdict(ok)+" (K="+std::to_string(k)+" contact steps)","  HS pairs crossing DF40s : "+std::to_string(n_pairs),"  HS-pair contacts        : "+std::to_string(n_pair_contacts),"  failing contacts        : "+std::to_string(n_fail()),"  worst nearest-GND dist  : "+(worst_distance?std::to_string(*worst_distance):"n/a")+" (budget K="+std::to_string(k)+")","  nearest-GND distance distribution (dist: count):"};
    for(const auto& [d,n]:dist_hist)l.push_back("    "+pad(std::to_string(d),2,true)+" steps : "+std::to_string(n));l.push_back("  per-connector (pairs, pair-contacts, failing):");
    for(const auto& [ref,c]:per_conn){auto n=pairs_per_conn.find(ref);l.push_back("    "+ref+": "+std::to_string(n==pairs_per_conn.end()?0:n->second)+" pairs, "+std::to_string(c.first)+" pair-contacts, "+std::to_string(c.second)+" failing");}
    if(!violations.empty()){l.push_back("  VIOLATIONS:");auto sorted=violations;std::sort(sorted.begin(),sorted.end(),[](const auto& a,const auto& b){return std::tie(a.ref,a.base,a.net,a.pad)<std::tie(b.ref,b.base,b.net,b.pad);});for(const auto& v:sorted)l.push_back("    "+v.as_line());}return join(l);
}
} // namespace schgen
