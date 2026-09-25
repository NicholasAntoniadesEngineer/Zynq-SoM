#pragma once
#include "schgen/atomic_file.hpp"
#include "schgen/emit.hpp"
#include "schgen/pack.hpp"
#include "schgen/pcb_emit.hpp"
#include "schgen/turn.hpp"
#include <algorithm>
#include <charconv>
#include <cmath>
#include <functional>
#include <limits>
#include <sstream>

namespace schgen::pcb_emission {
using Uid = std::function<std::string(const std::string &)>;
using Points = std::vector<std::pair<double, double>>;
inline Sexpr sym(std::string s) { return Sexpr{Sexpr::Sym{std::move(s)}}; }
inline Sexpr str(std::string s) { return Sexpr{std::move(s)}; }
inline Sexpr num(double d) { return Sexpr{d}; }
inline Sexpr node(std::string name, std::initializer_list<Sexpr> values) {
    SexprList v{sym(std::move(name))};
    v.insert(v.end(), values);
    return Sexpr{std::move(v)};
}
inline bool tag(const Sexpr &n, const std::string &s) {
    auto a = std::get_if<SexprList>(&n.v);
    return a && !a->empty() && std::holds_alternative<Sexpr::Sym>((*a)[0].v) &&
           std::get<Sexpr::Sym>((*a)[0].v).name == s;
}
inline Sexpr *child(Sexpr &n, const std::string &s) {
    if (auto a = std::get_if<SexprList>(&n.v))
        for (auto &c : *a)
            if (tag(c, s))
                return &c;
    return nullptr;
}
inline bool starts(const std::string &s, const std::string &p) {
    return s.compare(0, p.size(), p) == 0;
}
inline const std::string *lookup(const ProjectStrings &v, const std::string &key) {
    for (const auto &[k, s] : v)
        if (k == key)
            return &s;
    return nullptr;
}
inline std::string fmt(double x, int precision = 6, bool fixed = false) {
    char b[768];
    auto r =
        std::to_chars(b, b + sizeof b, x,
                      fixed ? std::chars_format::fixed : std::chars_format::general, precision);
    if (r.ec != std::errc{})
        throw PcbEmissionError("PCB number formatting failed");
    return {b, r.ptr};
}
inline std::string pyfloat(double x) {
    if (!std::isfinite(x))
        throw PcbEmissionError("PCB nonfinite number");
    char b[768];
    auto r = std::to_chars(b, b + sizeof b, std::abs(x), std::chars_format::scientific);
    if (r.ec != std::errc{})
        throw PcbEmissionError("PCB number formatting failed");
    std::string s(b, r.ptr), sign = std::signbit(x) ? "-" : "";
    auto e = s.find('e');
    int exponent = std::stoi(s.substr(e + 1));
    if (exponent < -4 || exponent >= 16)
        return sign + s;
    std::string digits = s.substr(0, e);
    auto dot = digits.find('.');
    if (dot != digits.npos)
        digits.erase(dot, 1);
    int point = exponent + 1;
    if (point <= 0)
        return sign + "0." + std::string(-point, '0') + digits;
    if (point >= static_cast<int>(digits.size()))
        return sign + digits + std::string(point - digits.size(), '0') + ".0";
    digits.insert(static_cast<std::size_t>(point), ".");
    return sign + digits;
}
inline void publish(const std::filesystem::path &p, const std::string &s) {
    std::filesystem::create_directories(p.parent_path().empty() ? std::filesystem::path(".")
                                                                : p.parent_path());
    write_atomic_file(p, {s.begin(), s.end()});
}
inline const JsonNode &kind(const JsonNode &n, JsonKind k) {
    if (n.kind != k)
        throw PcbEmissionError("PCB transport: wrong JSON type");
    return n;
}
inline const JsonNode &required(const JsonNode &n, const std::string &k) {
    kind(n, JsonKind::Object);
    auto p = object_field(n, k);
    if (!p)
        throw PcbEmissionError("PCB transport: missing " + k);
    return *p;
}
inline double jnum(const JsonNode &n) {
    double d = kind(n, JsonKind::Number).number_value;
    if (!std::isfinite(d))
        throw PcbEmissionError("PCB transport: nonfinite number");
    return d;
}
inline int jint(const JsonNode &n) {
    double d = jnum(n);
    if (d != std::trunc(d) || d < std::numeric_limits<int>::min() ||
        d > std::numeric_limits<int>::max())
        throw PcbEmissionError("PCB transport: invalid integer");
    return static_cast<int>(d);
}
inline std::string jstr(const JsonNode &n) { return kind(n, JsonKind::String).string_value; }
inline bool jbool(const JsonNode &n) { return kind(n, JsonKind::Bool).bool_value; }
inline JsonNode j(double n) {
    JsonNode v;
    v.kind = JsonKind::Number;
    v.number_value = n;
    return v;
}
inline JsonNode j(const std::string &s) {
    JsonNode v;
    v.kind = JsonKind::String;
    v.string_value = s;
    return v;
}
inline JsonNode jb(bool b) {
    JsonNode v;
    v.kind = JsonKind::Bool;
    v.bool_value = b;
    return v;
}
inline JsonNode ja(std::vector<JsonNode> a = {}) {
    JsonNode v;
    v.kind = JsonKind::Array;
    v.array_value = std::move(a);
    return v;
}
inline JsonNode jo(std::vector<std::pair<std::string, JsonNode>> a = {}) {
    JsonNode v;
    v.kind = JsonKind::Object;
    v.object_value = std::move(a);
    return v;
}
inline void set(JsonNode &n, const std::string &k, JsonNode v) {
    kind(n, JsonKind::Object);
    for (auto &[key, val] : n.object_value)
        if (key == k) {
            val = std::move(v);
            return;
        }
    n.object_value.emplace_back(k, std::move(v));
}
inline Box4 box(const JsonNode &n) {
    const auto &a = kind(n, JsonKind::Array).array_value;
    if (a.size() != 4)
        throw PcbEmissionError("PCB transport: box requires four coordinates");
    return {jnum(a[0]), jnum(a[1]), jnum(a[2]), jnum(a[3])};
}
inline JsonNode box_json(Box4 b) { return ja({j(b.x0), j(b.y0), j(b.x1), j(b.y1)}); }
Box4 courtyard(const PcbFootprintInst &);
Sexpr embed(const PcbFootprintInst &, const PcbEmitPolicy &, const Uid &);
struct ThermalNodes {
    std::vector<Sexpr> zones, vias;
};
ThermalNodes thermal_nodes(const PcbModel &, const PcbEmitPolicy &, const Uid &,
                           PcbEmissionResult &);
std::vector<Sexpr> descriptors(const PcbModel &, const PcbEmitPolicy &, const Uid &, const Sexpr &);
int declutter(const PcbModel &, Sexpr &);
} // namespace schgen::pcb_emission
