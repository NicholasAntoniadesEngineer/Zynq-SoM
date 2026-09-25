#pragma once
#include "bringup_internal.hpp"
#include "verification_internal.hpp"
#include <charconv>
#include <fstream>
#include <regex>

namespace schgen::manufacturing_detail {
using namespace bringup_detail;
inline std::string read(const std::filesystem::path& path) {
    std::ifstream f(path,std::ios::binary);if(!f)throw ProjectError("cannot read "+path.string());
    return {std::istreambuf_iterator<char>(f),{}};
}
inline std::string pyfloat(double x) {
    if(!std::isfinite(x))throw ProjectError("nonfinite manufacturing number");
    char b[768];auto r=std::to_chars(b,b+sizeof b,std::abs(x),std::chars_format::scientific);
    if(r.ec!=std::errc{})throw ProjectError("manufacturing number formatting failed");
    std::string s(b,r.ptr),sign=std::signbit(x)?"-":"";auto e=s.find('e');int exp=std::stoi(s.substr(e+1));
    if(exp < -4 || exp >= 16)return sign+s;
    std::string digits=s.substr(0,e);auto dot=digits.find('.');if(dot!=digits.npos)digits.erase(dot,1);int point=exp+1;
    if(point<=0)return sign+"0."+std::string(-point,'0')+digits;
    if(point>=static_cast<int>(digits.size()))return sign+digits+std::string(point-digits.size(),'0')+".0";
    digits.insert(static_cast<std::size_t>(point),".");return sign+digits;
}
inline std::string safe(const std::string& text) {
    std::string out;bool sep=false;
    for(unsigned char c:text)if((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')) {
        if(sep&&!out.empty())out+='_';out+=static_cast<char>(c);sep=false;
    }else sep=true;
    return out;
}
inline std::string first_chars(const std::string& s,std::size_t n) {
    std::string out;for(const auto& p:verification::utf8(s)){if(!n--)break;out+=p.second;}return out;
}
inline JsonNode j(const std::string& s){JsonNode n;n.kind=JsonKind::String;n.string_value=s;return n;}
inline JsonNode j(double d){JsonNode n;n.kind=JsonKind::Number;n.number_value=d;return n;}
inline JsonNode arr(std::vector<JsonNode> a={}){JsonNode n;n.kind=JsonKind::Array;n.array_value=std::move(a);return n;}
inline JsonNode obj(std::vector<std::pair<std::string,JsonNode>> o={}){JsonNode n;n.kind=JsonKind::Object;n.object_value=std::move(o);return n;}
inline JsonNode opt(const std::optional<double>& n){return n?j(*n):JsonNode{};}
inline JsonNode opt(const std::optional<std::string>& n){return n?j(*n):JsonNode{};}
inline std::string quote(const std::string& s) {
    std::string out="\"";
    for(const auto& [cp,bytes]:verification::utf8(s)) {
        switch(cp){case '"':out+="\\\"";break;case '\\':out+="\\\\";break;case '\b':out+="\\b";break;case '\f':out+="\\f";break;case '\n':out+="\\n";break;case '\r':out+="\\r";break;case '\t':out+="\\t";break;
        default:if(cp<32||cp>=127){if(cp>0xffff){out+="\\u"+hex(0xd800+((cp-0x10000)>>10),4,false);out+="\\u"+hex(0xdc00+((cp-0x10000)&1023),4,false);}else out+="\\u"+hex(cp,4,false);}else out+=bytes;}
    }return out+'"';
}
inline std::string dump(const JsonNode& n,int level=0,const std::string& field="") {
    if(n.kind==JsonKind::Null)return "null";
    if(n.kind==JsonKind::Bool)return n.bool_value?"true":"false";
    if(n.kind==JsonKind::String)return quote(n.string_value);
    if(n.kind==JsonKind::Number){static const std::set<std::string> floats{"volts","limit_a","load_a","amps","cost"};return floats.count(field)?pyfloat(n.number_value):fixed(n.number_value,0);}
    const bool object=n.kind==JsonKind::Object;std::string out=object?"{":"[";
    auto fields=n.object_value;std::sort(fields.begin(),fields.end(),[](const auto& a,const auto& b){return a.first<b.first;});
    const auto count=object?fields.size():n.array_value.size();
    for(std::size_t i=0;i<count;++i){out+=i?",\n":"\n";out+=std::string(level+2,' ');if(object)out+=quote(fields[i].first)+": "+dump(fields[i].second,level+2,fields[i].first);else out+=dump(n.array_value[i],level+2,field);}
    if(count)out+='\n'+std::string(level,' ');return out+(object?"}":"]");
}
} // namespace schgen::manufacturing_detail
