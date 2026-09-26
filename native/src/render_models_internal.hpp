#pragma once
#include "schgen/atomic_file.hpp"
#include <algorithm>
#include <charconv>
#include <cctype>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace schgen::render_models_detail {
inline std::string read(const std::filesystem::path& p) {
    std::ifstream f(p, std::ios::binary);
    if (!f) throw std::runtime_error("cannot read " + p.string());
    std::string s{std::istreambuf_iterator<char>(f), {}};
    if (f.bad()) throw std::runtime_error("cannot read " + p.string());
    return s;
}
inline void write(const std::filesystem::path& p, const std::string& s) {
    write_atomic_file(p.string(), {s.begin(), s.end()});
}
inline std::string fixed(double x, int digits) {
    char b[768];
    const auto r = std::to_chars(b,b+sizeof b,x,std::chars_format::fixed,digits);
    if (r.ec != std::errc{}) throw std::runtime_error("model3d number out of range");
    return {b,r.ptr};
}
inline double number(const std::string& s) {
    std::size_t n=0;
    const double v=std::stod(s,&n);
    if (n!=s.size() || !std::isfinite(v)) throw std::runtime_error("invalid model3d number: "+s);
    return v;
}
inline std::string join(const std::vector<std::string>& v, const std::string& sep) {
    std::string out;
    for (const auto& s:v) { if (&s!=&v.front()) out+=sep; out+=s; }
    return out;
}
inline std::string trim(std::string s) {
    const auto first=s.find_first_not_of(" \t\r\n\v\f");
    if (first==s.npos) return {};
    return s.substr(first,s.find_last_not_of(" \t\r\n\v\f")-first+1);
}
inline std::vector<std::string> words(const std::string& s) {
    std::istringstream in(s); std::vector<std::string> out; std::string word;
    while (in>>word) out.push_back(word);
    return out;
}
inline std::vector<std::string> lines(const std::string& s) {
    std::istringstream in(s); std::vector<std::string> out; std::string line;
    while (std::getline(in,line)) out.push_back(line);
    return out;
}
inline void replace(std::string& s,const std::string& from,const std::string& to) {
    for (std::size_t p=0;(p=s.find(from,p))!=s.npos;p+=to.size()) s.replace(p,from.size(),to);
}
}
