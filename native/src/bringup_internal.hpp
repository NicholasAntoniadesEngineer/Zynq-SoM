#pragma once
#include "schgen/firmware_docs.hpp"
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <locale>
#include <map>
#include <set>
#include <sstream>
#include <unordered_map>
#include <type_traits>

namespace schgen::bringup_detail {
inline bool starts(const std::string& s, const std::string& p) { return s.rfind(p, 0) == 0; }
inline bool ends(const std::string& s, const std::string& p) {
    return s.size() >= p.size() && s.compare(s.size()-p.size(), p.size(), p) == 0;
}
inline bool has(const std::string& s, const std::string& p) { return s.find(p) != std::string::npos; }
inline std::string remove_prefix(const std::string& s, const std::string& p) {
    return starts(s,p) ? s.substr(p.size()) : s;
}
template<class T> bool contains(const std::vector<T>& v, const T& x) {
    return std::find(v.begin(),v.end(),x) != v.end();
}
inline std::string join(const std::vector<std::string>& xs, const std::string& sep) {
    std::string out;
    for (std::size_t i=0;i<xs.size();++i) { if(i) out+=sep; out+=xs[i]; }
    return out;
}
inline std::string hex(int n, int width=2, bool upper=true) {
    std::ostringstream o; if(upper) o << std::uppercase;
    o << std::hex << std::setfill('0') << std::setw(width) << n; return o.str();
}
inline std::string fixed(double n, int digits) {
    std::ostringstream o; o.imbue(std::locale::classic());
    o << std::fixed << std::setprecision(digits) << n; return o.str();
}
inline std::string general(double n) {
    std::ostringstream o; o.imbue(std::locale::classic()); o << std::setprecision(6) << n; return o.str();
}
// Python round uses ties-to-even. Decimal round first rounds the exact binary
// value via the standard decimal formatter, avoiding multiply-round artifacts.
inline long long rounded(double n) {
    if(!std::isfinite(n))throw FirmwareDocsError("cannot round a non-finite bring-up value");
    auto r=std::round(n);
    if(std::abs(n-r)==0.5&&std::fmod(r,2.0)!=0)r+=n<0?1:-1;
    if(r < -9223372036854775808.0 || r >= 9223372036854775808.0)
        throw FirmwareDocsError("bring-up integer exceeds signed 64-bit range");
    return static_cast<long long>(r);
}
inline double decimal_round(double n, int d) { return std::stod(fixed(n,d)); }
template<class T> std::string py(const std::optional<T>& x) {
    if (!x) return "None";
    if constexpr(std::is_same_v<T,std::string>) return *x;
    else return std::to_string(*x);
}
inline std::string quoted(const std::string& s) { return "'"+s+"'"; }
inline std::string repr(const std::vector<std::string>& xs) {
    std::vector<std::string> q; for(const auto& x:xs) q.push_back(quoted(x));
    return "["+join(q,", ")+"]";
}
inline std::string repr(const std::optional<std::string>& x) { return x ? quoted(*x) : "None"; }
inline std::string ascii(std::string s) {
    for(const auto& [from,to]:ProjectStrings{{"—","--"},{"→","->"}}) {
        std::size_t p=0; while((p=s.find(from,p))!=std::string::npos) {s.replace(p,from.size(),to);p+=to.size();}
    } return s;
}
inline std::pair<char,int> ref_key(const std::string& ref) {
    const auto tail=ref.substr(1);
    const bool digits=!tail.empty() && std::all_of(tail.begin(),tail.end(),[](unsigned char c){return c>='0'&&c<='9';});
    return {ref.empty()?'\0':ref.front(), digits?std::stoi(tail):0};
}
inline std::string lookup(const ProjectStrings& v,const std::string& key,const std::string& fallback="") {
    for(const auto& p:v) if(p.first==key) return p.second; return fallback;
}
} // namespace schgen::bringup_detail
