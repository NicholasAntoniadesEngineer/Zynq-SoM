#pragma once
#include "pcb_checks_internal.hpp"
#include "schgen/pcb_escape.hpp"

namespace schgen::pcb_escape {
using namespace pcb_checks;
inline constexpr double radius = 1.8, lattice = .05, lane_handle = 1., hole_hole = .5;
inline const std::vector<std::pair<double, double>> &ladder() {
    static const std::vector<std::pair<double, double>> v{{.45, .3}, {.4, .25}, {.35, .2}};
    return v;
}
inline ViaClear clear() { return {.10, .30, .10, hole_hole}; }
inline std::map<std::string, std::pair<double, double>> positions(const PcbCheckFootprint &fp) {
    std::map<std::string, std::pair<double, double>> out;
    for (const auto &p : fp.pads)
        if (!std::get<0>(p).empty())
            out[std::get<0>(p)] = {std::get<2>(p), std::get<3>(p)};
    return out;
}
inline const PcbCheckFootprint &footprint(const PcbCheckInstance &i) {
    if (!i.mod)
        throw PcbEscapeError(i.ref + ": escape footprint unresolved");
    return *i.mod;
}
inline std::pair<double, double> board(const PcbCheckInstance &i, double u, double v) {
    return uv_to_board(i.x, i.y, u, v, i.rotation == 0 ? 0.0 : i.rotation);
}
inline std::string point_repr(double u, double v) {
    return "(" + pyfloat(u) + ", " + pyfloat(v) + ")";
}
struct Connector {
    std::size_t index;
    std::map<std::string, std::pair<double, double>> pads;
    ContactGeom contacts;
};
inline std::map<std::string, Connector> prepare_connectors(const PcbCheckModel &m) {
    std::map<std::string, Connector> out;
    for (const auto &[ref, i] : connectors(m)) {
        const auto &fp = footprint(m.insts[i]);
        out.emplace(ref, Connector{i, positions(fp), pcb_escape_contact_geometry(fp)});
    }
    return out;
}
inline JsonNode obj(std::vector<std::pair<std::string, JsonNode>> v = {}) {
    JsonNode n;
    n.kind = JsonKind::Object;
    n.object_value = std::move(v);
    return n;
}
inline JsonNode arr(std::vector<JsonNode> v = {}) {
    JsonNode n;
    n.kind = JsonKind::Array;
    n.array_value = std::move(v);
    return n;
}
inline JsonNode str(const std::string &v) {
    JsonNode n;
    n.kind = JsonKind::String;
    n.string_value = v;
    return n;
}
inline JsonNode num(double v) {
    JsonNode n;
    n.kind = JsonKind::Number;
    n.number_value = v;
    return n;
}
inline JsonNode boolean(bool v) {
    JsonNode n;
    n.kind = JsonKind::Bool;
    n.bool_value = v;
    return n;
}
inline JsonNode strings(const std::vector<std::string> &v) {
    auto n = arr();
    for (const auto &s : v)
        n.array_value.push_back(str(s));
    return n;
}
inline JsonNode box(Box4 b) { return arr({num(b.x0), num(b.y0), num(b.x1), num(b.y1)}); }
} // namespace schgen::pcb_escape
