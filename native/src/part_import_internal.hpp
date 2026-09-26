#pragma once

#include "schgen/part_import.hpp"
#include <algorithm>
#include <charconv>
#include <cmath>
#include <limits>
#include <locale>
#include <map>
#include <sstream>
#include <string_view>

namespace schgen::part_import_detail {
using S = Sexpr;
inline S sym(const std::string& s) { return S{S::Sym{s}}; }
inline S str(const std::string& s) { return S{s}; }
inline S num(double n) { return S{n}; }
inline S list(std::initializer_list<S> s) { return S{SexprList(s)}; }
inline SexprList& items(S& s) { return std::get<SexprList>(s.v); }
inline const SexprList& items(const S& s) { return std::get<SexprList>(s.v); }
inline void append(S& s, S n) { items(s).push_back(std::move(n)); }
inline bool tag(const S& s, const std::string& t) {
    const auto* a = std::get_if<SexprList>(&s.v);
    if (!a || a->empty()) return false;
    const auto* v = std::get_if<S::Sym>(&a->front().v);
    return v && v->name == t;
}
inline const JsonNode& field(const JsonNode& v, const std::string& k) {
    static const JsonNode empty;
    if(v.kind==JsonKind::Null)return empty;
    const auto* p = object_field(v, k); return p ? *p : empty;
}
inline std::string string(const JsonNode& v, const std::string& fallback = {}) {
    return v.kind == JsonKind::String ? v.string_value : fallback;
}
inline std::string get(const JsonNode& v, const std::string& k, const std::string& fallback = {}) {
    return string(field(v,k), fallback);
}
inline bool truth(const JsonNode& v) {
    switch (v.kind) {
    case JsonKind::Null: return false;
    case JsonKind::Bool: return v.bool_value;
    case JsonKind::Number: return v.number_value != 0;
    case JsonKind::String: return !v.string_value.empty();
    case JsonKind::Array: return !v.array_value.empty();
    case JsonKind::Object: return !v.object_value.empty();
    }
    return false;
}
inline std::string trim(const std::string& s) {
    const auto i=s.find_first_not_of(" \t\n\r\v\f");
    return i==s.npos ? "" : s.substr(i,s.find_last_not_of(" \t\n\r\v\f")-i+1);
}
inline std::vector<std::string> split(const std::string& s, const std::string& sep) {
    std::vector<std::string> out; std::size_t from=0, at=0;
    while ((at=s.find(sep,from))!=s.npos) { out.push_back(s.substr(from,at-from)); from=at+sep.size(); }
    out.push_back(s.substr(from)); return out;
}
inline std::vector<std::string> words(const std::string& s) {
    std::istringstream in(s); in.imbue(std::locale::classic());
    std::vector<std::string> out; std::string word;
    while (in>>word) out.push_back(word);
    return out;
}
inline double number(const std::string& s, double fallback=0) {
    const auto value=trim(s); if (value.empty()) return fallback;
    double out=0;
    const char* first=value.data(); if (*first=='+') ++first;
    const auto r=std::from_chars(first,value.data()+value.size(),out);
    if (r.ec!=std::errc{} || r.ptr!=value.data()+value.size()) return fallback;
    if (!std::isfinite(out)) throw PartImportError("non-finite EasyEDA number");
    return out;
}
inline double number(const JsonNode& v, double fallback=0) {
    if (v.kind==JsonKind::Number) {
        if (!std::isfinite(v.number_value)) throw PartImportError("non-finite EasyEDA number");
        return v.number_value;
    }
    return v.kind==JsonKind::Bool ? (v.bool_value ? 1 : 0) : number(string(v),fallback);
}
inline int integer(double x) {
    if (!std::isfinite(x) || x<std::numeric_limits<int>::min() || x>std::numeric_limits<int>::max())
        throw PartImportError("EasyEDA integer outside supported range");
    return static_cast<int>(x);
}
// Decimal conversion of the exact binary value, ties-to-even, like Python round.
// Multiplying by 10^n before nearbyint changes half-way cases and is not equivalent.
inline double rounded(double x, int digits=4) {
    if (!std::isfinite(x)) throw PartImportError("non-finite EasyEDA geometry");
    char buf[768]; const auto r=std::to_chars(buf,buf+sizeof buf,x,std::chars_format::fixed,digits);
    if (r.ec!=std::errc{}) throw PartImportError("EasyEDA geometry outside supported range");
    return number(std::string(buf,r.ptr));
}
inline double mm(const std::string& v) { return rounded(number(v)*0.254,6); }
inline double rotation(double x) { double r=std::fmod(x,360); return r<0 ? r+360 : r; }
inline S effects(double size=1.27) { return list({sym("effects"),list({sym("font"),list({sym("size"),num(size),num(size)})})}); }
inline S stroke(double width) { return list({sym("stroke"),list({sym("width"),num(rounded(std::max(width,0.01)))}),list({sym("type"),sym("solid")})}); }
inline bool digits(const std::string& s) {
    return !s.empty() && std::all_of(s.begin(),s.end(),[](unsigned char c){return c>='0' && c<='9';});
}
inline std::string upper(std::string s) {
    for(auto& c:s) if(c>='a' && c<='z') c=static_cast<char>(c-'a'+'A');
    return s;
}
inline std::string join(const std::vector<std::string>& strings, const std::string& sep) {
    std::string out; for(const auto& s:strings) { if(&s!=&strings.front())out+=sep;out+=s; }return out;
}
void validate_component(const std::string& name);
std::string read_file(const std::filesystem::path& path);
std::string quote(const std::string& text);
std::vector<S> paste_grid(const std::string& number,double x,double y,double w,double h,double rot);
} // namespace schgen::part_import_detail
