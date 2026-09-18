#pragma once

#include "schgen/thermal_checks.hpp"
#include "schgen/atomic_file.hpp"
#include "schgen/occupancy.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <fstream>
#include <functional>
#include <iterator>
#include <limits>
#include <map>
#include <regex>
#include <sstream>
#include <tuple>

namespace schgen::model_checks {

template<class T, class K> auto find(T& entries, const K& key) {
    auto it = std::find_if(entries.begin(), entries.end(), [&](const auto& e) { return e.first == key; });
    return it == entries.end() ? nullptr : &it->second;
}
template<class T> auto sorted(const T& entries) {
    auto out = entries;
    std::stable_sort(out.begin(), out.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
    return out;
}
template<class T, class K, class V> void set(T& entries, K key, V value) {
    if (auto* existing = find(entries, key)) *existing = std::move(value);
    else entries.emplace_back(std::move(key), std::move(value));
}
inline bool starts(const std::string& s, const std::string& prefix) { return s.compare(0, prefix.size(), prefix) == 0; }
inline bool ends(const std::string& s, const std::string& suffix) { return s.size() >= suffix.size() && s.compare(s.size()-suffix.size(), suffix.size(), suffix) == 0; }
inline void replace_all(std::string& s, const std::string& from, const std::string& to) {
    for (std::size_t pos=0; (pos=s.find(from,pos))!=std::string::npos; pos+=to.size()) s.replace(pos,from.size(),to);
}
inline unsigned codepoint(const std::string& s,std::size_t& i) {
    const auto byte=static_cast<unsigned char>(s[i++]);
    if(byte<128)return byte;
    int extra=(byte&0xe0)==0xc0?1:(byte&0xf0)==0xe0?2:(byte&0xf8)==0xf0?3:0;
    unsigned cp=byte&((1u<<(6-extra))-1);
    if(!extra||i+extra>s.size())return byte;
    for(int k=0;k<extra;++k){auto c=static_cast<unsigned char>(s[i]);if((c&0xc0)!=0x80)return byte;cp=(cp<<6)|(c&63);++i;}
    return cp;
}
inline bool whitespace(unsigned cp) {
    return (cp>=9&&cp<=13)||(cp>=0x1c&&cp<=0x20)||cp==0x85||cp==0xa0||cp==0x1680||(cp>=0x2000&&cp<=0x200a)||cp==0x2028||cp==0x2029||cp==0x202f||cp==0x205f||cp==0x3000;
}
inline std::string trim(const std::string& s) {
    std::size_t begin=s.size(),end=0,i=0;
    while(i<s.size()){auto start=i;auto cp=codepoint(s,i);if(!whitespace(cp)){begin=std::min(begin,start);end=i;}}
    return begin==s.size()?"":s.substr(begin,end-begin);
}
inline std::string numeric_text(const std::string& s,bool spaces=false) {
    // Python 3.14's Unicode Nd blocks. Normalize decimal digits, not other
    // numeric glyphs (superscripts/Roman numerals are deliberately not digits).
    constexpr unsigned zeros[]={0x30,0x660,0x6f0,0x7c0,0x966,0x9e6,0xa66,0xae6,0xb66,0xbe6,0xc66,0xce6,0xd66,0xde6,0xe50,0xed0,0xf20,0x1040,0x1090,0x17e0,0x1810,0x1946,0x19d0,0x1a80,0x1a90,0x1b50,0x1bb0,0x1c40,0x1c50,0xa620,0xa8d0,0xa900,0xa9d0,0xa9f0,0xaa50,0xabf0,0xff10,0x104a0,0x10d30,0x10d40,0x11066,0x110f0,0x11136,0x111d0,0x112f0,0x11450,0x114d0,0x11650,0x116c0,0x116d0,0x116da,0x11730,0x118e0,0x11950,0x11bf0,0x11c50,0x11d50,0x11da0,0x11f50,0x16130,0x16a60,0x16ac0,0x16b50,0x16d70,0x1ccf0,0x1d7ce,0x1d7d8,0x1d7e2,0x1d7ec,0x1d7f6,0x1e140,0x1e2f0,0x1e4f0,0x1e5f1,0x1e950,0x1fbf0};
    std::string out;
    for(std::size_t i=0;i<s.size();) {
        auto start=i;unsigned cp=codepoint(s,i);bool digit=false;
        for(auto zero:zeros)if(cp>=zero&&cp-zero<10){out+=char('0'+cp-zero);digit=true;break;}
        if(!digit){if(spaces&&whitespace(cp))out+=' ';else out+=s.substr(start,i-start);}
    }
    return out;
}
inline std::string upper(std::string s) { for (char& c:s) if(c>='a'&&c<='z') c=char(c-'a'+'A'); return s; }
inline std::size_t chars(const std::string& s) {
    return std::count_if(s.begin(),s.end(),[](unsigned char c){return (c&0xc0)!=0x80;});
}
inline std::string pad(std::string s, std::size_t width, bool right=false) {
    auto n=chars(s); if(n>=width) return s;
    return right ? std::string(width-n,' ')+s : s+std::string(width-n,' ');
}
inline std::string fmt(double x, int digits=6, bool fixed=false) {
    char out[768];
    auto r=std::to_chars(out,out+sizeof out,x,fixed?std::chars_format::fixed:std::chars_format::general,digits);
    if(r.ec!=std::errc{}) throw ModelCheckError("model checks: numeric format out of range");
    return {out,r.ptr};
}
inline std::string f(double x,int digits) {return fmt(x,digits,true);}
inline std::string g(double x) {return fmt(x);}
// CPython 3.12+ float sum uses compensated addition. The distinction matters
// at the 10 uF inlet-capacitance boundary, before any report rounding occurs.
struct FloatSum {
    double hi=0,lo=0;
    void add(double x){double t=hi+x;lo+=std::fabs(hi)>=std::fabs(x)?(hi-t)+x:(x-t)+hi;hi=t;}
    double value()const{return lo!=0&&std::isfinite(lo)?hi+lo:hi;}
};
inline std::string repr(const std::string& s) {
    char q=s.find('\'')!=std::string::npos && s.find('"')==std::string::npos ? '"':'\'';
    std::string out(1,q);
    for(unsigned char c:s) {
        if(c==q||c=='\\') {out+='\\';out+=char(c);}
        else if(c=='\n')out+="\\n";else if(c=='\r')out+="\\r";else if(c=='\t')out+="\\t";
        else if(c<32||c==127) {const char* h="0123456789abcdef";out+="\\x";out+=h[c>>4];out+=h[c&15];}
        else out+=char(c);
    }
    return out+q;
}
inline std::string join(const std::vector<std::string>& lines,const std::string& sep="\n") {
    std::string out;for(const auto& l:lines){if(&l!=&lines.front())out+=sep;out+=l;}return out;
}
inline std::string read(const std::filesystem::path& path) {
    std::ifstream in(path,std::ios::binary); if(!in)throw ModelCheckError("model checks: cannot read "+path.string());
    std::string s((std::istreambuf_iterator<char>(in)),{}); if(in.bad())throw ModelCheckError("model checks: cannot read "+path.string());return s;
}
inline void publish(const std::filesystem::path& path,const std::string& text) {
    if(!path.parent_path().empty())std::filesystem::create_directories(path.parent_path());
    write_atomic_file(path.string(),{text.begin(),text.end()});
}

// Owned indexes are read-only views over one caller-owned sheet. A pin's first
// containing net wins, matching Circuit.net_of, even for malformed intermediates.
struct ModelSheetIndex {
    const CircuitSheetIr& c;
    std::map<std::string,const CircuitPartIr*> parts;
    std::map<std::pair<std::string,std::string>,const CircuitNetIr*> pins;
    explicit ModelSheetIndex(const CircuitSheetIr& circuit):c(circuit) {
        for(const auto& p:c.parts) parts[p.ref]=&p;
        for(const auto& n:c.nets)for(const auto& p:n.pins)pins.emplace(std::make_pair(p.ref,p.pin),&n);
    }
    const CircuitNetIr* net(const std::string& ref,const std::string& pin)const {
        auto it=pins.find({ref,pin});return it==pins.end()?nullptr:it->second;
    }
    const CircuitPartIr* part(const std::string& ref)const {auto it=parts.find(ref);return it==parts.end()?nullptr:it->second;}
    const CircuitNetIr* alias_net(const CircuitPartIr& p,const std::string& alias)const {
        for(const auto& a:p.pin_names)if(a.name==alias)return a.numbers.empty()?nullptr:net(p.ref,a.numbers.front());
        return net(p.ref,alias);
    }
};
inline std::string field(const CircuitPartIr& p,const std::string& key) {
    for(const auto& e:p.fields)if(e.key==key)return e.value;return {};
}
inline auto sorted_regs(const PowerCheckResult& power) {
    std::vector<const PowerReg*> out;for(const auto& r:power.regs)out.push_back(&r);
    std::stable_sort(out.begin(),out.end(),[](auto a,auto b){return std::tie(a->sheet,a->ref)<std::tie(b->sheet,b->ref);});return out;
}
inline ModelWaivers waivers(const std::vector<ProjectCircuit>& sheets,const std::string& kind) {
    ModelWaivers out;for(const auto& s:sheets)for(const auto& w:s.circuit.waivers)if(w.kind==kind)set(out,s.name+":"+w.key,std::make_pair(s.name,w.reason));return out;
}
inline JsonNode j(const std::string& s){JsonNode n;n.kind=JsonKind::String;n.string_value=s;return n;}
inline JsonNode j(const char* s){return j(std::string(s));}
inline JsonNode j(double d){JsonNode n;n.kind=JsonKind::Number;n.number_value=d;return n;}
inline JsonNode j(bool b){JsonNode n;n.kind=JsonKind::Bool;n.bool_value=b;return n;}
inline JsonNode obj(std::initializer_list<std::pair<std::string,JsonNode>> fs={}){JsonNode n;n.kind=JsonKind::Object;n.object_value=fs;return n;}
inline JsonNode arr(std::initializer_list<JsonNode> fs={}){JsonNode n;n.kind=JsonKind::Array;n.array_value=fs;return n;}
inline JsonNode strings(const std::vector<std::string>& ss){auto n=arr();for(const auto& s:ss)n.array_value.push_back(j(s));return n;}
template<class T> JsonNode opt(const std::optional<T>& x){return x?j(*x):JsonNode{};}
inline JsonNode waiver_json(const ModelWaivers& ws){auto n=obj();for(const auto& [k,v]:ws)n.object_value.emplace_back(k,arr({j(v.first),j(v.second)}));return n;}
inline JsonNode number_map(const std::vector<std::pair<std::string,double>>& es){auto n=obj();for(const auto& [k,v]:es)n.object_value.emplace_back(k,j(v));return n;}

inline void shape(const JsonNode& n,JsonKind kind,const std::string& where) {
    if(n.kind!=kind)throw ModelCheckError(where+": wrong JSON type");
}
inline void object_shape(const JsonNode& n,const std::set<std::string>& keys,const std::string& where) {
    shape(n,JsonKind::Object,where);std::set<std::string> seen;
    for(const auto& [k,v]:n.object_value){(void)v;if(!keys.count(k)||!seen.insert(k).second)throw ModelCheckError(where+": unexpected or duplicate field '"+k+"'");}
    for(const auto& k:keys)if(!seen.count(k))throw ModelCheckError(where+": missing field '"+k+"'");
}
inline const JsonNode& member(const JsonNode& n,const std::string& key) {
    auto p=object_field(n,key);if(!p)throw ModelCheckError("model result: missing field '"+key+"'");return *p;
}
inline std::string string(const JsonNode& n) {shape(n,JsonKind::String,"model result string");return n.string_value;}
inline double number(const JsonNode& n) {shape(n,JsonKind::Number,"model result number");if(!std::isfinite(n.number_value))throw ModelCheckError("model result: nonfinite number");return n.number_value;}
inline bool boolean(const JsonNode& n) {shape(n,JsonKind::Bool,"model result bool");return n.bool_value;}
inline std::size_t count(const JsonNode& n) {
    double d=number(n);if(d<0||d>=std::ldexp(1.0,std::numeric_limits<std::size_t>::digits)||std::floor(d)!=d)throw ModelCheckError("model result: invalid count");return static_cast<std::size_t>(d);
}
inline int signed_int(const JsonNode& n) {
    double d=number(n);if(d<std::numeric_limits<int>::min()||d>std::numeric_limits<int>::max()||std::floor(d)!=d)throw ModelCheckError("model result: invalid integer");return static_cast<int>(d);
}
inline const std::vector<JsonNode>& array_items(const JsonNode& n){shape(n,JsonKind::Array,"model result array");return n.array_value;}
inline const std::vector<JsonNode>& tuple_items(const JsonNode& n,std::size_t len){auto& a=array_items(n);if(a.size()!=len)throw ModelCheckError("model result: wrong tuple length");return a;}
inline std::vector<std::string> read_strings(const JsonNode& n){std::vector<std::string> out;for(const auto& x:array_items(n))out.push_back(string(x));return out;}
inline void unique_map(const JsonNode& n) {
    shape(n,JsonKind::Object,"model result map");std::set<std::string> seen;for(const auto& [k,v]:n.object_value){(void)v;if(!seen.insert(k).second)throw ModelCheckError("model result: duplicate map key '"+k+"'");}
}
inline ModelWaivers read_waivers(const JsonNode& n) {
    unique_map(n);ModelWaivers out;for(const auto& [k,v]:n.object_value){auto& a=tuple_items(v,2);out.emplace_back(k,std::make_pair(string(a[0]),string(a[1])));}return out;
}
inline std::vector<std::pair<std::string,double>> read_number_map(const JsonNode& n) {
    unique_map(n);std::vector<std::pair<std::string,double>> out;for(const auto& [k,v]:n.object_value)out.emplace_back(k,number(v));return out;
}

} // namespace schgen::model_checks
