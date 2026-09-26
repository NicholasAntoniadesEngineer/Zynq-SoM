#pragma once
#include "pcb_checks_internal.hpp"
#include "schgen/legalize.hpp"
#include "schgen/pcb_placement_gates.hpp"
#include "schgen/ratsnest_gate.hpp"

namespace schgen::placement_gates {
using namespace pcb_checks;
using Boxes = std::map<std::string, Box4>;
using Point = FloorplanPoint;
inline const JsonNode &opt(const JsonNode &n, const std::string &key) {
    static const JsonNode nil;
    if (n.kind == JsonKind::Null)
        return nil;
    kind(n, JsonKind::Object);
    auto p = object_field(n, key);
    return p ? *p : nil;
}
inline std::string str(const JsonNode &n, const std::string &key,
                       const std::string &fallback = "") {
    const auto &v = opt(n, key);
    return v.kind == JsonKind::Null ? fallback : jstr(v);
}
inline double num(const JsonNode &n, const std::string &key, double fallback = 0) {
    const auto &v = opt(n, key);
    return v.kind == JsonKind::Null ? fallback : jnum(v);
}
inline bool truth(const JsonNode &n) {
    switch (n.kind) {
    case JsonKind::Null:
        return false;
    case JsonKind::Bool:
        return n.bool_value;
    case JsonKind::Array:
        return !n.array_value.empty();
    case JsonKind::Object:
        return !n.object_value.empty();
    case JsonKind::String:
        return !n.string_value.empty();
    case JsonKind::Number:
        return n.number_value != 0;
    }
    return false;
}
inline const std::vector<JsonNode> &array(const JsonNode &n) {
    static const std::vector<JsonNode> empty;
    return n.kind == JsonKind::Null ? empty : kind(n, JsonKind::Array).array_value;
}
inline std::vector<std::string> strings(const JsonNode &n) {
    std::vector<std::string> out;
    for (const auto &v : array(n))
        out.push_back(jstr(v));
    return out;
}
inline void unique_add(std::vector<std::string> &out, const std::string &s) {
    if (std::find(out.begin(), out.end(), s) == out.end())
        out.push_back(s);
}
inline std::string dist(std::optional<double> d) { return d ? f(*d, 2) + "mm" : "n/a"; }
inline std::optional<double> gap(const Boxes *a, const Boxes *b,
                                 const std::vector<std::string> *pins = nullptr) {
    if (!a || !b)
        return {};
    std::optional<double> best;
    for (const auto &[p, ab] : *a)
        if (!pins || std::find(pins->begin(), pins->end(), p) != pins->end())
            for (const auto &[q, bb] : *b) {
                (void)q;
                double d = box_gap(ab, bb);
                if (!best || d < *best)
                    best = d;
            }
    return best;
}
inline std::optional<double> minimum(std::optional<double> a, std::optional<double> b) {
    return !a ? b : !b ? a : std::min(*a, *b);
}
inline bool over(std::optional<double> d, double lim) { return !d || *d > lim; }
inline bool under(std::optional<double> d, double lim) { return d && *d < lim; }
inline const std::map<std::string, std::string> &refs(const PcbPlacementGatePolicy &p,
                                                      const std::string &sheet) {
    static const std::map<std::string, std::string> empty;
    auto f = p.ref_maps.find(sheet);
    return f == p.ref_maps.end() ? empty : f->second;
}
inline std::string root(const std::string &s) { return s.substr(0, s.find('.')); }
inline std::string point_repr(Point p) {
    return "(" + pyfloat(p.first) + ", " + pyfloat(p.second) + ")";
}
struct FinalGeometry {
    const PcbCheckInput &input;
    std::map<std::string, Point> centroids;
    std::map<std::string, Box4> bboxes;
    explicit FinalGeometry(const PcbCheckInput &);
    std::optional<Point> centroid(const std::string &) const;
    std::optional<Box4> bbox(const std::string &) const;
    std::optional<Point> members(const std::string &, const std::set<std::string> &) const;
};
} // namespace schgen::placement_gates
