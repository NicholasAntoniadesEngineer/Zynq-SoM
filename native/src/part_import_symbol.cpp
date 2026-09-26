#include "part_import_internal.hpp"
#include "schgen/pack.hpp"
#include <regex>
#include <set>

namespace schgen {
namespace {
using namespace part_import_detail;
const std::regex ground("^(GND|GNDA|GNDD|PGND|AGND|DGND|VSS|EP$|EPAD|PAD$|EXPOSED)",std::regex::icase);
const std::regex power("^(VDD|VCC|VBUS|VBAT|VIN|V\\+|AVDD|DVDD|VDDA|VDDIO|\\+[0-9])",std::regex::icase);
const std::regex nc("^(NC|N\\.C\\.?|DNC)$",std::regex::icase);
bool matches(const std::string& s,const std::regex& re) { return std::regex_search(s,re); }
double ceil_grid(double v,double step=2.54) { return rounded(std::ceil(v/step-1e-9)*step); }
double max_width(const std::vector<CatalogPin>& pins,bool names) {
    double w=0; for(const auto& p:pins) w=std::max(w,text_wh(names?p.name:p.number,1.27,0.95,1.6).first);
    return w;
}
double pin_length(const std::vector<CatalogPin>& pins) { return std::max(2.54,ceil_grid(max_width(pins,false)+0.6,1.27)); }
S pin_node(const CatalogPin& p,double x,double y,double angle,double length) {
    return list({sym("pin"),sym(p.etype),sym("line"),list({sym("at"),num(x),num(y),num(angle)}),
                 list({sym("length"),num(length)}),list({sym("name"),str(p.name),effects()}),
                 list({sym("number"),str(p.number),effects()})});
}
std::string numeric_key(const std::string& s) {
    const auto at=s.find_first_not_of('0'); return at==s.npos?"0":s.substr(at);
}
bool pin_number_less(const CatalogPin& a,const CatalogPin& b) {
    const bool ad=digits(a.number),bd=digits(b.number);
    if(ad!=bd)return ad;
    if(ad) { const auto x=numeric_key(a.number),y=numeric_key(b.number);
        if(x.size()!=y.size())return x.size()<y.size();
        if(x!=y)return x<y;
    }
    return a.number<b.number;
}
}

PartImportInfo part_import_info(const JsonNode& result) {
    const auto& cp=field(field(field(result,"dataStr"),"head"),"c_para");
    PartImportInfo out; auto& p=out.part;
    p.lcsc=get(field(result,"lcsc"),"number");
    if(p.lcsc.empty())p.lcsc=get(field(result,"szlcsc"),"number");
    p.mpn=get(cp,"Manufacturer Part");if(p.mpn.empty())p.mpn=get(cp,"name");if(p.mpn.empty())p.mpn=p.lcsc;
    p.prefix=get(cp,"pre");if(p.prefix.empty())p.prefix="U?";
    while(!p.prefix.empty() && p.prefix.back()=='?')p.prefix.pop_back();if(p.prefix.empty())p.prefix="U";
    p.package=get(cp,"package"); p.manufacturer=get(cp,"Manufacturer");p.jlc_class=get(cp,"JLCPCB Part Class");
    p.description=get(result,"description");if(p.description.empty())p.description=get(result,"title",p.mpn)+" ("+p.package+")";
    p.product_url=get(field(result,"lcsc"),"url");
    p.datasheet=p.lcsc.empty()?"":"https://www.lcsc.com/datasheet/"+p.lcsc+".pdf";
    for(const auto& tag:field(result,"tags").array_value) {
        if(tag.kind!=JsonKind::String)throw PartImportError("EasyEDA tag must be a string");
        out.tags.push_back(tag.string_value);
    }
    return out;
}

std::vector<CatalogPin> part_import_pins(const JsonNode& result) {
    static const std::map<int,std::string> types{{0,"passive"},{1,"input"},{2,"output"},{3,"bidirectional"},{4,"power_in"}};
    std::vector<CatalogPin> out;
    for(const auto& line:field(field(result,"dataStr"),"shape").array_value) {
        const auto raw=string(line);if(raw.compare(0,2,"P~")!=0)continue;
        std::vector<std::vector<std::string>> seg;for(const auto& s:split(raw,"^^"))seg.push_back(split(s,"~"));
        const int type=seg[0].size()>2?integer(number(seg[0][2])):0;
        const auto it=types.find(type);
        std::string number=seg.size()>4 && seg[4].size()>4?seg[4][4]:"";
        if(number.empty() && seg[0].size()>3)number=seg[0][3];
        std::string name=seg.size()>3 && seg[3].size()>4?seg[3][4]:"";
        if(name.empty())name=number;
        out.push_back({number,name,it==types.end()?"passive":it->second});
    }
    if(out.empty())throw PartImportError("EasyEDA symbol has no pins");
    return out;
}

std::vector<CatalogPin> part_normalize_pin_types(std::vector<CatalogPin> pins,const std::string& prefix) {
    static const std::set<std::string> passive{"R","C","L","FB","F"};
    if(pins.size()<=2 || passive.count(prefix) || std::all_of(pins.begin(),pins.end(),[](const auto& p){return p.etype=="input";}))
        for(auto& p:pins)p.etype="passive";
    return pins;
}

std::string part_safe_name(const std::string& name) {
    std::string out;
    for(const unsigned char c:name) {
        const bool safe=(c>='a' && c<='z') || (c>='A' && c<='Z') || (c>='0' && c<='9') || c=='.' || c=='_' || c=='-';
        if(safe)out+=static_cast<char>(c);else if(out.empty() || out.back()!='_')out+='_';
    }
    const auto first=out.find_first_not_of('_');if(first==out.npos)return {};
    return out.substr(first,out.find_last_not_of('_')-first+1);
}

std::optional<CatalogPin> part_synthesize_ep(const std::string& lcsc,const std::vector<CatalogPin>& pins) {
    if(lcsc!="C3192119")return std::nullopt;
    std::string maximum;
    for(const auto& p:pins) {
        const auto name=upper(p.name);if(name=="EP" || name=="PAD" || name=="EPAD")return std::nullopt;
        if(digits(p.number)) { const auto n=numeric_key(p.number);
            if(n.size()>maximum.size() || (n.size()==maximum.size() && n>maximum))maximum=n;
        }
    }
    if(maximum.empty())return CatalogPin{"EP","EP","passive"};
    std::size_t i=maximum.size();while(i && maximum[i-1]=='9'){maximum[--i]='0';}
    if(i)++maximum[i-1];else maximum.insert(0,"1");
    return CatalogPin{maximum,"EP","passive"};
}

PartPinGroups part_group_pins(const std::vector<CatalogPin>& pins) {
    PartPinGroups g;
    const bool named_power=std::any_of(pins.begin(),pins.end(),[](const auto& p){return matches(p.name,ground)||matches(p.name,power)||p.etype=="power_in";});
    const bool all_signal=std::all_of(pins.begin(),pins.end(),[](const auto& p){return p.etype=="passive"||p.etype=="bidirectional";});
    if(all_signal && !named_power) {
        if(pins.size()>6 && std::all_of(pins.begin(),pins.end(),[](const auto& p){return digits(p.number);})) {
            for(const auto& p:pins)(p.number.back()%2 ? g.left:g.right).push_back(p);
        } else if(pins.size()==2) {
            auto ordered=pins;std::stable_sort(ordered.begin(),ordered.end(),pin_number_less);
            g.left.push_back(ordered[0]);g.right.push_back(ordered[1]);
        } else {
            const auto half=(pins.size()+1)/2;
            g.left.assign(pins.begin(),pins.begin()+static_cast<std::ptrdiff_t>(half));
            g.right.assign(pins.begin()+static_cast<std::ptrdiff_t>(half),pins.end());
        }
        return g;
    }
    for(const auto& p:pins) {
        if(matches(p.name,nc)||matches(p.name,ground))g.bottom.push_back(p);
        else if(matches(p.name,power)||p.etype=="power_in")g.top.push_back(p);
        else if(p.etype=="input")g.left.push_back(p);
        else g.right.push_back(p);
    }
    if(g.left.empty() && g.right.size()>4) {
        std::vector<std::string> names;
        for(const auto& p:g.right)if(std::find(names.begin(),names.end(),p.name)==names.end())names.push_back(p.name);
        const std::set<std::string> half(names.begin(),names.begin()+static_cast<std::ptrdiff_t>((names.size()+1)/2));
        auto right=std::move(g.right);g.right.clear();
        for(const auto& p:right)(half.count(p.name)?g.left:g.right).push_back(p);
    }
    return g;
}

Sexpr part_generate_symbol(const std::string& name,const std::vector<CatalogPin>& pins,const PartImportInfo& info) {
    const auto g=part_group_pins(pins);
    const bool hide=std::all_of(pins.begin(),pins.end(),[](const auto& p){return p.name==p.number;});
    const double l=hide?0:max_width(g.left,true),r=hide?0:max_width(g.right,true);
    const double t=hide?0:max_width(g.top,true),b=hide?0:max_width(g.bottom,true);
    constexpr double off=0.508,pitch=2.54;
    const double width=std::max({ceil_grid(l+r+2*off+pitch),ceil_grid((std::max(g.top.size(),g.bottom.size())+1)*pitch),2*pitch});
    const double pt=(!g.top.empty() && t)?ceil_grid(t+off+1.27):0;
    const double pb=(!g.bottom.empty() && b)?ceil_grid(b+off+1.27):0;
    const double height=std::max({ceil_grid((std::max(g.left.size(),g.right.size())+1)*pitch)+pt+pb,ceil_grid(t+b+2*off+pitch),2*pitch});
    const double hw=width/2,hh=height/2;
    const double ll=pin_length(g.left),lr=pin_length(g.right),lt=pin_length(g.top),lb=pin_length(g.bottom);
    S pin_nodes=list({sym("symbol"),str(name+"_1_1")});
    for(std::size_t i=0;i<g.left.size();++i)append(pin_nodes,pin_node(g.left[i],-hw-ll,hh-pt-pitch*(i+1),0,ll));
    for(std::size_t i=0;i<g.right.size();++i)append(pin_nodes,pin_node(g.right[i],hw+lr,hh-pt-pitch*(i+1),180,lr));
    for(std::size_t i=0;i<g.top.size();++i)append(pin_nodes,pin_node(g.top[i],-pitch*(static_cast<double>(g.top.size())-1)/2+pitch*i,hh+lt,270,lt));
    for(std::size_t i=0;i<g.bottom.size();++i)append(pin_nodes,pin_node(g.bottom[i],-pitch*(static_cast<double>(g.bottom.size())-1)/2+pitch*i,-hh-lb,90,lb));
    const auto body=list({sym("rectangle"),list({sym("start"),num(-hw),num(hh)}),list({sym("end"),num(hw),num(-hh)}),
        list({sym("stroke"),list({sym("width"),num(0.254)}),list({sym("type"),sym("default")})}),list({sym("fill"),list({sym("type"),sym("background")})})});
    auto prop=[](const std::string& key,const std::string& value,double y,bool hidden) {
        auto e=effects();if(hidden)append(e,list({sym("hide"),sym("yes")}));
        return list({sym("property"),str(key),str(value),list({sym("at"),num(0),num(y),num(0)}),std::move(e)});
    };
    auto names=list({sym("pin_names"),list({sym("offset"),num(off)})});if(hide)append(names,list({sym("hide"),sym("yes")}));
    const auto& p=info.part;
    const auto symbol=list({sym("symbol"),str(name),std::move(names),list({sym("exclude_from_sim"),sym("no")}),
        list({sym("in_bom"),sym("yes")}),list({sym("on_board"),sym("yes")}),
        prop("Reference",p.prefix,hh+lt+1.27,false),prop("Value",p.mpn,-hh-lb-1.27,false),
        prop("Footprint",name+":"+name,0,true),prop("Datasheet",p.datasheet,0,true),
        prop("Description",p.description,0,true),prop("LCSC",p.lcsc,0,true),
        list({sym("symbol"),str(name+"_0_1"),body}),std::move(pin_nodes)});
    return list({sym("kicad_symbol_lib"),list({sym("version"),num(20241209)}),list({sym("generator"),str("schgen_part_gen")}),
                 list({sym("generator_version"),str("1.0")}),symbol});
}
} // namespace schgen
