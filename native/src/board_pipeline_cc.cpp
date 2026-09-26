#include "board_pipeline_internal.hpp"
#include "schgen/cc.hpp"
#include "schgen/quantize.hpp"
#include <map>
#include <set>

namespace schgen {
namespace {
using Pin=std::pair<std::string,std::string>;
struct Node {GeomNode geometry;std::set<Pin> pins;std::set<std::string> names;};
std::string point(GeomKey k){return "("+std::to_string(k.first)+", "+std::to_string(k.second)+")";}
std::string repr(const std::string& s){std::string out="'";for(char c:s){if(c=='\\'||c=='\'')out+='\\';if(c=='\n')out+="\\n";else out+=c;}return out+'\'';}
std::string strings(std::vector<std::string> xs){std::sort(xs.begin(),xs.end());for(auto& x:xs)x=repr(x);return "["+board_pipeline_detail::join(xs)+"]";}
}
BoardCcResult check_board_sheet_cc(const CircuitSheetIr& c,const SchematicRoutePlacement& p,
    const SchematicRoutedSheet& routed,const SchematicSymbolResolver& resolve){
    std::map<GeomKey,Node> nodes;
    auto node=[&](double x,double y)->Node&{const auto k=geom_key(x,y);auto [it,fresh]=nodes.emplace(k,Node{});
        if(fresh)it->second.geometry={k.first,k.second,py_round(x,4),py_round(y,4)};return it->second;};
    std::map<Pin,std::vector<std::pair<double,double>>> tips;
    for(const auto& part:p.parts)for(const auto& pin:resolve(part.lib_id).pins){
        const auto xy=pin_page_position(pin,part.x,part.y,part.rotation);const Pin key{part.ref,pin.number};
        node(xy.first,xy.second).pins.insert(key);tips[key].push_back(xy);}
    for(const auto& pw:p.powers)node(pw.x,pw.y).names.insert(pw.net_name());
    for(const auto& label:p.hlabels)node(label.x,label.y).names.insert(label.name);
    for(const auto& label:p.llabels)node(label.x,label.y).names.insert(label.name);
    std::vector<GeomSeg> segs;for(const auto& s:routed.segs){node(s.x0,s.y0);node(s.x1,s.y1);segs.push_back({s.x0,s.y0,s.x1,s.y1});}
    for(const auto& j:routed.junctions)node(j.x,j.y);
    std::vector<GeomBond> bonds;for(const auto& [pin,xy]:tips){(void)pin;for(std::size_t i=1;i<xy.size();++i)bonds.push_back({xy[i-1].first,xy[i-1].second,xy[i].first,xy[i].second});}
    std::vector<GeomNode> raw;for(const auto& [key,n]:nodes){(void)key;raw.push_back(n.geometry);}
    const auto roots=seed_geometry_unions(raw,segs,bonds);std::map<GeomKey,GeomKey> parent;
    for(std::size_t i=0;i<raw.size();++i)parent[{raw[i].kx,raw[i].ky}]=roots.at(i);
    auto root=[&](GeomKey k){while(parent.at(k)!=k)k=parent.at(k);return k;};
    std::map<std::string,GeomKey> named;
    for(const auto& [key,n]:nodes)for(const auto& name:n.names){auto [it,fresh]=named.emplace(name,key);if(!fresh){const auto a=root(key),b=root(it->second);parent[std::max(a,b)]=std::min(a,b);}}
    std::map<Pin,std::string> declared;std::set<std::string> declared_names;
    for(const auto& net:c.nets){declared_names.insert(net.name);for(const auto& pin:net.pins)declared[{pin.ref,pin.pin}]=net.name;}
    std::map<GeomKey,std::set<std::string>> nets;std::map<GeomKey,std::vector<Pin>> pins;std::map<Pin,GeomKey> pin_root;std::set<GeomKey> components;
    for(const auto& [key,n]:nodes){const auto r=root(key);components.insert(r);
        for(const auto& pin:n.pins){pin_root[pin]=r;pins[r].push_back(pin);if(declared.count(pin))nets[r].insert(declared.at(pin));}
        for(const auto& name:n.names)if(declared_names.count(name))nets[r].insert(name);}
    BoardCcResult out;out.sheet=c.name;out.n_components=components.size();out.n_declared=c.nets.size();
    for(const auto& [r,ns]:nets)if(ns.size()>1){auto ps=pins[r];std::sort(ps.begin(),ps.end());std::vector<std::string> detail;
        for(const auto& pin:ps)if(declared.count(pin))detail.push_back(pin.first+"."+pin.second+"="+declared.at(pin));
        out.shorts.push_back("component @grid"+point(r)+" merges declared nets "+strings({ns.begin(),ns.end()})+" ["+board_pipeline_detail::join(detail)+"]");}
    for(const auto& net:c.nets){std::map<GeomKey,std::vector<std::string>> spans;std::vector<std::string> missing;
        for(const auto& pnet:net.pins){const Pin pin{pnet.ref,pnet.pin};const auto label=pin.first+"."+pin.second;
            if(pin_root.count(pin))spans[pin_root.at(pin)].push_back(label);else missing.push_back(label);}
        if(net.pins.size()>=2 && spans.size()>1){std::vector<std::string> detail;for(const auto& [r,ps]:spans)detail.push_back("comp"+point(r)+": "+strings(ps));
            out.opens.push_back("declared net "+repr(net.name)+" ("+net.net_class+") split across "+std::to_string(spans.size())+" components: "+board_pipeline_detail::join(detail," | "));}
        if(!missing.empty())out.opens.push_back("declared net "+repr(net.name)+": pin(s) "+strings(missing)+" have no geometry node (un-placed terminal)");}
    return out;
}
std::string BoardCcResult::summary() const {
    const auto tag="CC GATE"+std::string(sheet.empty()?"":" ["+sheet+"]");
    if(ok())return tag+": PASS ("+std::to_string(n_declared)+" declared nets, "+std::to_string(n_components)+" geometry components — agree)";
    std::string s=tag+": FAIL";for(const auto& x:shorts)s+="\n  SHORT: "+x;for(const auto& x:opens)s+="\n  OPEN: "+x;return s;
}
}
