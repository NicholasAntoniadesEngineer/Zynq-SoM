#include "schgen/pcb_scan.hpp"

#include "schgen/embed_fp.hpp"
#include "schgen/emit.hpp"
#include "schgen/pack.hpp"
#include "schgen/sexpr.hpp"

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

namespace schgen {
namespace {

bool is_sym(const Sexpr& node, const char* name) {
    return std::holds_alternative<Sexpr::Sym>(node.v)
        && std::get<Sexpr::Sym>(node.v).name == name;
}

bool is_tagged_list(const Sexpr& node, const char* name) {
    if (!std::holds_alternative<SexprList>(node.v)) {
        return false;
    }
    const SexprList& lst = std::get<SexprList>(node.v);
    return !lst.empty() && is_sym(lst[0], name);
}

const SexprList* find_tagged_child(const SexprList& node, const char* tag) {
    for (const Sexpr& child : node) {
        if (!std::holds_alternative<SexprList>(child.v)) {
            continue;
        }
        const SexprList& lst = std::get<SexprList>(child.v);
        if (!lst.empty() && is_sym(lst[0], tag)) {
            return &lst;
        }
    }
    return nullptr;
}

std::string py_str(const Sexpr& node) {
    if (std::holds_alternative<std::string>(node.v)) {
        return std::get<std::string>(node.v);
    }
    if (std::holds_alternative<Sexpr::Sym>(node.v)) {
        return std::get<Sexpr::Sym>(node.v).name;
    }
    if (std::holds_alternative<double>(node.v)) {
        const double value = std::get<double>(node.v);
        const auto as_int = static_cast<std::int64_t>(value);
        if (static_cast<double>(as_int) == value) {
            return std::to_string(as_int);
        }
        return sexpr_fmt_num(value);
    }
    if (std::holds_alternative<bool>(node.v)) {
        return std::get<bool>(node.v) ? "True" : "False";
    }
    throw std::runtime_error("pcb_scan: cannot stringify");
}

bool is_number(const Sexpr& node) {
    return std::holds_alternative<double>(node.v);
}

bool is_gfx_geom(const Sexpr& head) {
    const std::string tag = py_str(head);
    return tag == "fp_line" || tag == "fp_rect" || tag == "fp_circle"
        || tag == "fp_arc" || tag == "fp_poly";
}

}  // namespace

std::pair<std::vector<std::pair<double, double>>, double> silk_gfx_pts(
    const Sexpr& node) {
    if (!std::holds_alternative<SexprList>(node.v)) {
        throw std::runtime_error("silk_gfx_pts: list required");
    }
    const SexprList& lst = std::get<SexprList>(node.v);
    if (lst.empty()) {
        throw std::runtime_error("silk_gfx_pts: empty node");
    }
    std::vector<std::pair<double, double>> pts;
    if (py_str(lst[0]) == "fp_circle") {
        const SexprList* ctr = find_tagged_child(lst, "center");
        const SexprList* end = find_tagged_child(lst, "end");
        if (ctr != nullptr && end != nullptr && ctr->size() >= 3
            && end->size() >= 3 && is_number((*ctr)[1]) && is_number((*ctr)[2])
            && is_number((*end)[1]) && is_number((*end)[2])) {
            const double cxf = std::get<double>((*ctr)[1].v);
            const double cyf = std::get<double>((*ctr)[2].v);
            const double dx = std::get<double>((*end)[1].v) - cxf;
            const double dy = std::get<double>((*end)[2].v) - cyf;
            const double radius = std::sqrt(dx * dx + dy * dy);
            pts.emplace_back(cxf - radius, cyf - radius);
            pts.emplace_back(cxf + radius, cyf + radius);
        }
    } else {
        for (const char* tag : {"start", "mid", "end", "center"}) {
            const SexprList* p = find_tagged_child(lst, tag);
            if (p != nullptr && p->size() >= 3 && is_number((*p)[1])
                && is_number((*p)[2])) {
                pts.emplace_back(std::get<double>((*p)[1].v),
                                 std::get<double>((*p)[2].v));
            }
        }
        const SexprList* ptsn = find_tagged_child(lst, "pts");
        if (ptsn != nullptr) {
            for (const Sexpr& xy : *ptsn) {
                if (!std::holds_alternative<SexprList>(xy.v)) {
                    continue;
                }
                const SexprList& row = std::get<SexprList>(xy.v);
                if (row.size() >= 3 && is_sym(row[0], "xy") && is_number(row[1])
                    && is_number(row[2])) {
                    pts.emplace_back(std::get<double>(row[1].v),
                                     std::get<double>(row[2].v));
                }
            }
        }
    }
    double half_width = 0.06;
    const SexprList* stroke = find_tagged_child(lst, "stroke");
    if (stroke != nullptr) {
        const SexprList* width = find_tagged_child(*stroke, "width");
        if (width != nullptr && width->size() >= 2 && is_number((*width)[1])) {
            half_width = std::get<double>((*width)[1].v) / 2.0;
        }
    }
    return {std::move(pts), half_width};
}

std::pair<std::vector<Box4>, std::vector<Box4>> collect_fp_silk_gfx(
    const Sexpr& footprint) {
    std::vector<Box4> top;
    std::vector<Box4> bot;
    if (!std::holds_alternative<SexprList>(footprint.v)) {
        return {top, bot};
    }
    const SexprList& node = std::get<SexprList>(footprint.v);
    if (node.empty() || py_str(node[0]) != "footprint") {
        return {top, bot};
    }
    const SexprList* fat = find_tagged_child(node, "at");
    if (fat == nullptr || fat->size() < 3 || !is_number((*fat)[1])
        || !is_number((*fat)[2])) {
        return {top, bot};
    }
    const double fx = std::get<double>((*fat)[1].v);
    const double fy = std::get<double>((*fat)[2].v);
    double angle = 0.0;
    if (fat->size() > 3 && is_number((*fat)[3])) {
        angle = std::get<double>((*fat)[3].v) * (M_PI / 180.0);
    }
    const double ca = std::cos(angle);
    const double sa = std::sin(angle);
    for (const Sexpr& child : node) {
        if (!std::holds_alternative<SexprList>(child.v)) {
            continue;
        }
        const SexprList& lst = std::get<SexprList>(child.v);
        if (lst.empty()) {
            continue;
        }
        try {
            if (!is_gfx_geom(lst[0])) {
                continue;
            }
        } catch (const std::runtime_error&) {
            continue;
        }
        const SexprList* lyr = find_tagged_child(lst, "layer");
        if (lyr == nullptr || lyr->size() < 2) {
            continue;
        }
        const std::string layer = py_str((*lyr)[1]);
        if (layer != "F.SilkS" && layer != "B.SilkS") {
            continue;
        }
        auto pts_hw = silk_gfx_pts(child);
        auto hit = silk_gfx_extent(pts_hw.first, fx, fy, ca, sa, pts_hw.second);
        if (!hit.has_value()) {
            continue;
        }
        (layer == "F.SilkS" ? top : bot).push_back(*hit);
    }
    return {std::move(top), std::move(bot)};
}

std::vector<std::tuple<int, int, std::string>> thermal_via_scan(
    const Sexpr& footprint,
    const std::unordered_map<std::string, std::pair<int, std::string>>&
        pad_nets) {
    std::vector<const Sexpr*> pads;
    if (std::holds_alternative<SexprList>(footprint.v)) {
        const SexprList& out = std::get<SexprList>(footprint.v);
        for (const Sexpr& node : out) {
            if (is_tagged_list(node, "pad")) {
                pads.push_back(&node);
            }
        }
    }
    std::vector<std::tuple<double, double, double, double, int, std::string>>
        netted;
    for (const Sexpr* node : pads) {
        const SexprList& lst = std::get<SexprList>(node->v);
        const std::string name = lst.size() > 1 ? py_str(lst[1]) : "";
        auto found = pad_nets.find(name);
        if (found == pad_nets.end() || found->second.first <= 0) {
            continue;
        }
        auto geom = pad_geom(*node);
        if (!geom.has_value()) {
            continue;
        }
        netted.emplace_back(geom->at_x, geom->at_y, geom->half_w, geom->half_h,
                            found->second.first, found->second.second);
    }
    std::vector<std::tuple<int, int, std::string>> out_map;
    if (netted.empty()) {
        return out_map;
    }
    for (int seq = 0; seq < static_cast<int>(pads.size()); ++seq) {
        const SexprList& lst = std::get<SexprList>(pads[static_cast<std::size_t>(seq)]->v);
        const std::string name = lst.size() > 1 ? py_str(lst[1]) : "";
        auto found = pad_nets.find(name);
        const int net_num = found == pad_nets.end() ? 0 : found->second.first;
        if (net_num > 0 || (name != "" && name != " ")) {
            continue;
        }
        auto geom = pad_geom(*pads[static_cast<std::size_t>(seq)]);
        if (!geom.has_value()) {
            continue;
        }
        auto hit = thermal_via_inherit(geom->at_x, geom->at_y, netted);
        if (hit.has_value()) {
            out_map.emplace_back(seq, hit->first, hit->second);
        }
    }
    return out_map;
}

double farm_row_right_bound(double extent_x0, double extent_x1_flow,
                            double a3_center_x, double titleblock_left,
                            double titleblock_margin, double cap_pitch) {
    const double flow_centre = (extent_x0 + extent_x1_flow) / 2.0;
    const double dx = a3_center_x - flow_centre;
    const double local_limit = (titleblock_left - titleblock_margin) - dx;
    return local_limit - cap_pitch / 2.0;
}

std::vector<std::string> conn_port_columns(const std::vector<double>& ys,
                                           double row_pitch, double eps) {
    std::vector<std::string> cols;
    cols.reserve(ys.size());
    bool have_prev = false;
    double prev_y = 0.0;
    std::string prev_col;
    for (double y : ys) {
        const std::string col =
            (have_prev && std::fabs(y - prev_y - row_pitch) < eps
             && prev_col == "inner")
                ? "outer"
                : "inner";
        cols.push_back(col);
        prev_y = y;
        prev_col = col;
        have_prev = true;
    }
    return cols;
}

std::vector<std::vector<int>> conn_cluster_groups(
    const std::vector<double>& ys, double row_pitch, double eps) {
    std::vector<std::vector<int>> groups;
    for (int i = 0; i < static_cast<int>(ys.size()); ++i) {
        if (!groups.empty()
            && std::fabs(ys[static_cast<std::size_t>(i)]
                         - ys[static_cast<std::size_t>(groups.back().back())]
                         - row_pitch)
                < eps) {
            groups.back().push_back(i);
        } else {
            groups.push_back({i});
        }
    }
    return groups;
}

}  // namespace schgen
