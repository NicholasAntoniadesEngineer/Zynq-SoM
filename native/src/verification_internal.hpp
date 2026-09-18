#pragma once
#include "model_checks_internal.hpp"

namespace schgen::verification {
using namespace model_checks;
inline std::vector<const CircuitPartIr*> ordered_parts(const CircuitSheetIr& c) {
    std::vector<const CircuitPartIr*> out; for(const auto& p:c.parts)out.push_back(&p);
    std::stable_sort(out.begin(),out.end(),[](auto a,auto b){return a->ref<b->ref;});return out;
}
inline void write_report(const std::filesystem::path& path,const std::string& text) {
    if(!path.parent_path().empty()&&!std::filesystem::is_directory(path.parent_path()))
        throw std::filesystem::filesystem_error("report directory does not exist",path.parent_path(),std::make_error_code(std::errc::no_such_file_or_directory));
    const auto payload=text+"\n";write_atomic_file(path.string(),{payload.begin(),payload.end()});
}
inline std::string list_repr(const std::vector<std::string>& values) {
    std::vector<std::string> quoted;for(const auto& v:values)quoted.push_back(repr(v));return "["+join(quoted,", ")+"]";
}
inline bool pin_less(const std::string& a,const std::string& b) {
    const auto ac=chars(a),bc=chars(b);return ac==bc?a<b:ac<bc;
}
inline std::string py_json_repr(const JsonNode& n) {
    switch(n.kind) {
    case JsonKind::Null:return "None";
    case JsonKind::Bool:return n.bool_value?"True":"False";
    case JsonKind::String:return repr(n.string_value);
    case JsonKind::Number: {
        char data[512];auto end=std::to_chars(data,data+sizeof data,n.number_value);
        if(end.ec!=std::errc{})throw std::runtime_error("catalog numeric value out of range");
        return {data,end.ptr};
    }
    case JsonKind::Array:{std::vector<std::string> v;for(const auto& x:n.array_value)v.push_back(py_json_repr(x));return "["+join(v,", ")+"]";}
    case JsonKind::Object:{std::vector<std::string> v;for(const auto& [k,x]:n.object_value)v.push_back(repr(k)+": "+py_json_repr(x));return "{"+join(v,", ")+"}";}
    }
    throw std::runtime_error("invalid catalog JSON kind");
}
inline std::string py_json_str(const JsonNode& n) {return n.kind==JsonKind::String?n.string_value:py_json_repr(n);}
inline bool truth(const JsonNode& n) {
    switch(n.kind) {
    case JsonKind::Null:return false;case JsonKind::Bool:return n.bool_value;
    case JsonKind::String:return !n.string_value.empty();case JsonKind::Number:return n.number_value!=0;
    case JsonKind::Array:return !n.array_value.empty();case JsonKind::Object:return !n.object_value.empty();
    }return false;
}
inline std::vector<std::pair<std::uint32_t,std::string>> utf8(const std::string& text) {
    std::vector<std::pair<std::uint32_t,std::string>> out;
    for(std::size_t i=0;i<text.size();) {
        const auto begin=i;auto c=static_cast<unsigned char>(text[i++]);std::uint32_t cp=c;
        int count=c<0x80?0:c<0xe0?1:c<0xf0?2:3;
        if(c>=0x80)cp=c&((1u<<(6-count))-1);
        for(int k=0;k<count&&i<text.size();++k)cp=(cp<<6)|(static_cast<unsigned char>(text[i++])&63);
        out.emplace_back(cp,text.substr(begin,i-begin));
    }return out;
}
inline bool space(std::uint32_t c) {
    return (c>=9&&c<=13)||(c>=28&&c<=32)||c==0x85||c==0xa0||c==0x1680||
        (c>=0x2000&&c<=0x200a)||c==0x2028||c==0x2029||c==0x202f||c==0x205f||c==0x3000;
}
inline std::string replace_invalid_utf8(const std::string& text) {
    std::string out;
    for(std::size_t i=0;i<text.size();) {
        const auto a=static_cast<unsigned char>(text[i]);
        if(a<0x80){out+=text[i++];continue;}
        const std::size_t size=a>=0xc2&&a<=0xdf?2:a>=0xe0&&a<=0xef?3:a>=0xf0&&a<=0xf4?4:0;
        if(!size){out+="�";++i;continue;}
        std::size_t valid=1;
        for(;valid<size&&i+valid<text.size();++valid) {
            const auto b=static_cast<unsigned char>(text[i+valid]);
            if((b&0xc0)!=0x80)break;
            if(valid==1&&((a==0xe0&&b<0xa0)||(a==0xed&&b>=0xa0)||(a==0xf0&&b<0x90)||(a==0xf4&&b>=0x90)))break;
        }
        if(valid==size){out+=text.substr(i,size);i+=size;}
        else {out+="�";i+=valid;}
    }return out;
}
inline std::string strip(const std::string& s) {
    const auto v=utf8(s);std::size_t a=0,b=v.size();while(a<b&&space(v[a].first))++a;while(b>a&&space(v[b-1].first))--b;
    std::string out;for(;a<b;++a)out+=v[a].second;return out;
}
inline std::string regex_numbers(const std::string& s) {
    // Unicode decimal digit blocks accepted by Python re's \d and float().
    static constexpr std::uint32_t starts[]={0x30,0x660,0x6f0,0x7c0,0x966,0x9e6,0xa66,0xae6,0xb66,0xbe6,0xc66,0xce6,0xd66,0xde6,0xe50,0xed0,0xf20,0x1040,0x1090,0x17e0,0x1810,0x1946,0x19d0,0x1a80,0x1a90,0x1b50,0x1bb0,0x1c40,0x1c50,0xa620,0xa8d0,0xa900,0xa9d0,0xa9f0,0xaa50,0xabf0,0xff10,0x104a0,0x10d30,0x11066,0x110f0,0x11136,0x111d0,0x112f0,0x11450,0x114d0,0x11650,0x116c0,0x11730,0x118e0,0x11950,0x11c50,0x11d50,0x11da0,0x16a60,0x16ac0,0x16b50,0x1d7ce,0x1d7d8,0x1d7e2,0x1d7ec,0x1d7f6,0x1e140,0x1e2f0,0x1e950,0x1fbf0};
    std::string out;for(const auto& [cp,bytes]:utf8(s)) {
        if(space(cp)){out+=' ';continue;}bool found=false;
        for(auto start:starts)if(cp>=start&&cp<start+10){out+=char('0'+cp-start);found=true;break;}
        if(!found)out+=bytes;
    }return out;
}
}  // namespace schgen::verification
