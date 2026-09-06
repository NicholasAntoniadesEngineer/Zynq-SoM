#include "schgen/pcb_scan.hpp"

#include "schgen/embed_fp.hpp"
#include "schgen/emit.hpp"
#include "schgen/occupancy.hpp"
#include "schgen/pack.hpp"
#include "schgen/quantize.hpp"
#include "schgen/sexpr.hpp"
#include "schgen/turn.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <optional>
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

SexprList* find_tagged_child_mut(SexprList& node, const char* tag) {
    for (Sexpr& child : node) {
        if (!std::holds_alternative<SexprList>(child.v)) {
            continue;
        }
        SexprList& lst = std::get<SexprList>(child.v);
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

double font_size_of(const SexprList& node, double default_size) {
    const SexprList* effects = find_tagged_child(node, "effects");
    if (effects == nullptr) {
        return default_size;
    }
    const SexprList* font = find_tagged_child(*effects, "font");
    if (font == nullptr) {
        return default_size;
    }
    const SexprList* size = find_tagged_child(*font, "size");
    if (size == nullptr || size->size() < 2 || !is_number((*size)[1])) {
        return default_size;
    }
    return std::get<double>((*size)[1].v);
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

std::vector<std::tuple<std::string, double, double, double, double>>
pad_boxes_local(
    const std::vector<std::tuple<std::string, double, double, double, double,
                                 double>>& rows,
    double rotation) {
    std::vector<std::tuple<std::string, double, double, double, double>> out;
    out.reserve(rows.size());
    const double rot = rotation;
    for (const auto& row : rows) {
        const auto turned = turn_point(std::get<1>(row), std::get<2>(row), rot);
        const auto half = pad_half_extent(std::get<4>(row), std::get<5>(row),
                                          rot + std::get<3>(row));
        out.emplace_back(std::get<0>(row), turned.first - half.first,
                         turned.second - half.second,
                         turned.first + half.first,
                         turned.second + half.second);
    }
    return out;
}

Box4 inst_placed_box(const Box4& local_bbox, double inst_x, double inst_y,
                     double rotation, int decimals) {
    const Box4 rotated = turn_box(local_bbox, rotation);
    return Box4{py_round(inst_x + rotated.x0, decimals),
                py_round(inst_y + rotated.y0, decimals),
                py_round(inst_x + rotated.x1, decimals),
                py_round(inst_y + rotated.y1, decimals)};
}

std::vector<Box4> collect_gr_text_boxes(const Sexpr& doc, double default_size) {
    std::vector<Box4> out;
    if (!std::holds_alternative<SexprList>(doc.v)) {
        return out;
    }
    for (const Sexpr& node : std::get<SexprList>(doc.v)) {
        if (!std::holds_alternative<SexprList>(node.v)) {
            continue;
        }
        const SexprList& lst = std::get<SexprList>(node.v);
        if (lst.size() < 2 || py_str(lst[0]) != "gr_text"
            || !std::holds_alternative<std::string>(lst[1].v)) {
            continue;
        }
        const SexprList* at = find_tagged_child(lst, "at");
        if (at == nullptr || at->size() < 3 || !is_number((*at)[1])
            || !is_number((*at)[2])) {
            continue;
        }
        out.push_back(text_box(std::get<std::string>(lst[1].v),
                               std::get<double>((*at)[1].v),
                               std::get<double>((*at)[2].v),
                               font_size_of(lst, default_size), 0.15));
    }
    return out;
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

std::vector<RefdesProp> collect_refdes_props(const Sexpr& doc,
                                             double default_size) {
    std::vector<RefdesProp> top;
    std::vector<RefdesProp> bot;
    if (!std::holds_alternative<SexprList>(doc.v)) {
        return {};
    }
    const SexprList& nodes = std::get<SexprList>(doc.v);
    for (int fi = 0; fi < static_cast<int>(nodes.size()); ++fi) {
        const Sexpr& node = nodes[static_cast<std::size_t>(fi)];
        if (!std::holds_alternative<SexprList>(node.v)) {
            continue;
        }
        const SexprList& fp = std::get<SexprList>(node.v);
        if (fp.empty()) {
            continue;
        }
        try {
            if (py_str(fp[0]) != "footprint") {
                continue;
            }
        } catch (const std::runtime_error&) {
            continue;
        }
        const SexprList* fat = find_tagged_child(fp, "at");
        if (fat == nullptr || fat->size() < 3 || !is_number((*fat)[1])
            || !is_number((*fat)[2])) {
            continue;
        }
        const double fx = std::get<double>((*fat)[1].v);
        const double fy = std::get<double>((*fat)[2].v);
        double frot = 0.0;
        if (fat->size() > 3 && is_number((*fat)[3])) {
            frot = std::get<double>((*fat)[3].v);
        }
        const double angle = frot * (M_PI / 180.0);
        const double ca = std::cos(angle);
        const double sa = std::sin(angle);
        const SexprList* flay = find_tagged_child(fp, "layer");
        bool bottom = false;
        if (flay != nullptr && flay->size() >= 2) {
            bottom = py_str((*flay)[1]) == "B.Cu";
        }
        const std::string want = bottom ? "B.SilkS" : "F.SilkS";
        for (int pi = 0; pi < static_cast<int>(fp.size()); ++pi) {
            const Sexpr& child = fp[static_cast<std::size_t>(pi)];
            if (!std::holds_alternative<SexprList>(child.v)) {
                continue;
            }
            const SexprList& prop = std::get<SexprList>(child.v);
            if (prop.size() <= 2) {
                continue;
            }
            try {
                if (py_str(prop[0]) != "property"
                    || py_str(prop[1]) != "Reference") {
                    continue;
                }
            } catch (const std::runtime_error&) {
                continue;
            }
            const SexprList* lay = find_tagged_child(prop, "layer");
            if (lay == nullptr || lay->size() < 2
                || py_str((*lay)[1]) != want) {
                continue;
            }
            const SexprList* hide = find_tagged_child(prop, "hide");
            if (hide != nullptr
                && (hide->size() < 2 || py_str((*hide)[1]) == "yes")) {
                continue;
            }
            const SexprList* lat = find_tagged_child(prop, "at");
            if (lat == nullptr || lat->size() < 3 || !is_number((*lat)[1])
                || !is_number((*lat)[2])) {
                continue;
            }
            RefdesProp hit;
            hit.footprint_index = fi;
            hit.property_index = pi;
            hit.ref = py_str(prop[2]);
            hit.fp_x = fx;
            hit.fp_y = fy;
            hit.cos_a = ca;
            hit.sin_a = sa;
            hit.local_x = std::get<double>((*lat)[1].v);
            hit.local_y = std::get<double>((*lat)[2].v);
            hit.size = font_size_of(prop, default_size);
            hit.bottom = bottom;
            const double bx = fx + hit.local_x * ca + hit.local_y * sa;
            const double by = fy - hit.local_x * sa + hit.local_y * ca;
            hit.text_box = text_box(hit.ref, bx, by, hit.size, 0.15);
            (bottom ? bot : top).push_back(std::move(hit));
        }
    }
    std::sort(top.begin(), top.end(),
              [](const RefdesProp& a, const RefdesProp& b) {
                  return a.ref < b.ref;
              });
    std::sort(bot.begin(), bot.end(),
              [](const RefdesProp& a, const RefdesProp& b) {
                  return a.ref < b.ref;
              });
    top.insert(top.end(), bot.begin(), bot.end());
    return top;
}

std::vector<RefdesRow> collect_refdes_rows(
    const Sexpr& doc,
    const std::unordered_map<std::string, Box4>& court_by_ref,
    double default_size) {
    auto hits = collect_refdes_props(doc, default_size);
    std::vector<RefdesRow> rows;
    rows.reserve(hits.size());
    for (const auto& hit : hits) {
        const double bx =
            hit.fp_x + hit.local_x * hit.cos_a + hit.local_y * hit.sin_a;
        const double by =
            hit.fp_y - hit.local_x * hit.sin_a + hit.local_y * hit.cos_a;
        RefdesRow row;
        row.footprint_index = hit.footprint_index;
        row.property_index = hit.property_index;
        row.ref = hit.ref;
        row.fp_x = hit.fp_x;
        row.fp_y = hit.fp_y;
        row.cos_a = hit.cos_a;
        row.sin_a = hit.sin_a;
        const auto found = court_by_ref.find(hit.ref);
        if (found != court_by_ref.end()) {
            row.court = found->second;
        } else {
            row.court = Box4{bx - 1.0, by - 1.0, bx + 1.0, by + 1.0};
        }
        row.size = hit.size;
        row.text_box = hit.text_box;
        row.bottom = hit.bottom;
        rows.push_back(std::move(row));
    }
    return rows;
}

std::string footprint_alias(
    const std::string& footprint,
    const std::vector<std::pair<std::string, std::string>>& aliases) {
    for (const auto& kv : aliases) {
        if (kv.first == footprint) {
            return kv.second;
        }
    }
    return footprint;
}

bool mirror_assert_ok(bool mirror, const std::string& side,
                      bool mirrored_path) {
    if (!mirror) {
        return true;
    }
    return side == "bottom" && mirrored_path;
}

bool needs_flag(const std::vector<std::string>& pin_etypes,
                const std::vector<std::string>& driver_etypes) {
    bool has_power_in = false;
    for (const auto& et : pin_etypes) {
        if (et == "power_in") {
            has_power_in = true;
            break;
        }
    }
    if (!has_power_in) {
        return false;
    }
    for (const auto& et : pin_etypes) {
        for (const auto& driver : driver_etypes) {
            if (et == driver) {
                return false;
            }
        }
    }
    return true;
}

std::tuple<double, double, double, double> farm_cluster_origin(
    double extent_x0, double extent_y1, double unit, int n_box_bucks) {
    const double col_x = gsnap(extent_x0 + 4.0 * unit, unit);
    const double row_step = gceil(8.0 * unit, unit);
    const double rise = (n_box_bucks >= 2 ? 12.0 : 8.0) * unit;
    const double cy = gceil(extent_y1 + rise, unit);
    return {col_x, col_x, row_step, cy};
}

double next_rail_col(double col_x, double cap_pitch, double prev_rail_w,
                     double rail_w, double unit, double extra) {
    const double need = std::max(cap_pitch, prev_rail_w / 2.0 + rail_w / 2.0
                                              + extra);
    return gceil(col_x - cap_pitch + need, unit);
}

Sexpr set_font_size(Sexpr prop, double size) {
    if (!std::holds_alternative<SexprList>(prop.v)) {
        throw std::runtime_error("set_font_size: property list required");
    }
    SexprList& node = std::get<SexprList>(prop.v);
    SexprList* effects = find_tagged_child_mut(node, "effects");
    if (effects == nullptr) {
        return prop;
    }
    SexprList* font = find_tagged_child_mut(*effects, "font");
    if (font == nullptr) {
        return prop;
    }
    const double sz = py_round(size, 3);
    SexprList* szn = find_tagged_child_mut(*font, "size");
    if (szn != nullptr && szn->size() >= 3) {
        (*szn)[1] = Sexpr{sz};
        (*szn)[2] = Sexpr{sz};
    }
    SexprList* thk = find_tagged_child_mut(*font, "thickness");
    if (thk != nullptr && thk->size() >= 2) {
        (*thk)[1] = Sexpr{py_round(std::max(0.1, size * 0.15), 3)};
    }
    return prop;
}

std::pair<Sexpr, int> hide_undersom_bottom_refs(
    Sexpr doc, double x0, double y0, double x1, double y1) {
    if (!std::holds_alternative<SexprList>(doc.v)) {
        throw std::runtime_error("hide_undersom_bottom_refs: list required");
    }
    SexprList& nodes = std::get<SexprList>(doc.v);
    int hidden = 0;
    for (Sexpr& node : nodes) {
        if (!std::holds_alternative<SexprList>(node.v)) {
            continue;
        }
        SexprList& fp = std::get<SexprList>(node.v);
        if (fp.empty()) {
            continue;
        }
        try {
            if (py_str(fp[0]) != "footprint") {
                continue;
            }
        } catch (const std::runtime_error&) {
            continue;
        }
        const SexprList* flay = find_tagged_child(fp, "layer");
        if (flay == nullptr || flay->size() < 2
            || py_str((*flay)[1]) != "B.Cu") {
            continue;
        }
        const SexprList* fat = find_tagged_child(fp, "at");
        if (fat == nullptr || fat->size() < 3 || !is_number((*fat)[1])
            || !is_number((*fat)[2])) {
            continue;
        }
        const double fx = std::get<double>((*fat)[1].v);
        const double fy = std::get<double>((*fat)[2].v);
        if (!(x0 <= fx && fx <= x1 && y0 <= fy && fy <= y1)) {
            continue;
        }
        for (Sexpr& child : fp) {
            if (!std::holds_alternative<SexprList>(child.v)) {
                continue;
            }
            SexprList& prop = std::get<SexprList>(child.v);
            if (prop.size() <= 2) {
                continue;
            }
            try {
                if (py_str(prop[0]) != "property"
                    || py_str(prop[1]) != "Reference") {
                    continue;
                }
            } catch (const std::runtime_error&) {
                continue;
            }
            SexprList* hide = find_tagged_child_mut(prop, "hide");
            if (hide != nullptr && hide->size() >= 2) {
                (*hide)[1] = Sexpr{Sexpr::Sym{"yes"}};
            } else {
                SexprList hide_node{Sexpr{Sexpr::Sym{"hide"}},
                                    Sexpr{Sexpr::Sym{"yes"}}};
                const auto at = std::min(static_cast<std::size_t>(3),
                                         prop.size());
                prop.insert(prop.begin() + static_cast<std::ptrdiff_t>(at),
                            Sexpr{std::move(hide_node)});
            }
            hidden += 1;
            break;
        }
    }
    return {std::move(doc), hidden};
}

namespace {

void footprint_bbox_walk(const SexprList& node, std::vector<double>* xs,
                         std::vector<double>* ys) {
    for (const Sexpr& child : node) {
        if (!std::holds_alternative<SexprList>(child.v)) {
            continue;
        }
        const SexprList& sub = std::get<SexprList>(child.v);
        if (sub.empty()) {
            continue;
        }
        const bool gfx = is_sym(sub[0], "fp_line") || is_sym(sub[0], "fp_rect")
            || is_sym(sub[0], "fp_poly") || is_sym(sub[0], "fp_circle")
            || is_sym(sub[0], "fp_arc");
        if (gfx) {
            const SexprList* lyr = find_tagged_child(sub, "layer");
            if (lyr == nullptr || lyr->size() <= 1) {
                continue;
            }
            const std::string layer = py_str((*lyr)[1]);
            if (layer.find("CrtYd") == std::string::npos) {
                continue;
            }
            if (is_sym(sub[0], "fp_circle")) {
                const SexprList* ctr = find_tagged_child(sub, "center");
                const SexprList* end = find_tagged_child(sub, "end");
                if (ctr != nullptr && end != nullptr && ctr->size() >= 3
                    && end->size() >= 3 && is_number((*ctr)[1])
                    && is_number((*ctr)[2]) && is_number((*end)[1])
                    && is_number((*end)[2])) {
                    const double cxf = std::get<double>((*ctr)[1].v);
                    const double cyf = std::get<double>((*ctr)[2].v);
                    const double dx = std::get<double>((*end)[1].v) - cxf;
                    const double dy = std::get<double>((*end)[2].v) - cyf;
                    const double radius = std::sqrt(dx * dx + dy * dy);
                    xs->push_back(cxf - radius);
                    ys->push_back(cyf - radius);
                    xs->push_back(cxf + radius);
                    ys->push_back(cyf + radius);
                }
            }
            for (const char* tag : {"start", "end", "mid", "center"}) {
                const SexprList* p = find_tagged_child(sub, tag);
                if (p != nullptr && p->size() >= 3 && is_number((*p)[1])
                    && is_number((*p)[2])) {
                    xs->push_back(std::get<double>((*p)[1].v));
                    ys->push_back(std::get<double>((*p)[2].v));
                }
            }
            const SexprList* ptsn = find_tagged_child(sub, "pts");
            if (ptsn != nullptr) {
                for (const Sexpr& xy : *ptsn) {
                    if (!std::holds_alternative<SexprList>(xy.v)) {
                        continue;
                    }
                    const SexprList& row = std::get<SexprList>(xy.v);
                    if (row.size() >= 3 && is_sym(row[0], "xy")
                        && is_number(row[1]) && is_number(row[2])) {
                        xs->push_back(std::get<double>(row[1].v));
                        ys->push_back(std::get<double>(row[2].v));
                    }
                }
            }
            continue;
        }
        if (is_sym(sub[0], "pad")) {
            const SexprList* at = find_tagged_child(sub, "at");
            const SexprList* size = find_tagged_child(sub, "size");
            if (at == nullptr || size == nullptr || at->size() < 3
                || size->size() < 3 || !is_number((*at)[1])
                || !is_number((*at)[2]) || !is_number((*size)[1])
                || !is_number((*size)[2])) {
                continue;
            }
            const double px = std::get<double>((*at)[1].v);
            const double py = std::get<double>((*at)[2].v);
            double deg = 0.0;
            if (at->size() > 3 && is_number((*at)[3])) {
                deg = std::get<double>((*at)[3].v);
            }
            const auto half = pad_half_extent(std::get<double>((*size)[1].v),
                                              std::get<double>((*size)[2].v),
                                              deg);
            xs->push_back(px - half.first);
            ys->push_back(py - half.second);
            xs->push_back(px + half.first);
            ys->push_back(py + half.second);
            continue;
        }
        footprint_bbox_walk(sub, xs, ys);
    }
}

}  // namespace

std::vector<double> scan_floats(const std::string& text) {
    std::vector<double> out;
    const std::size_t n = text.size();
    std::size_t i = 0;
    while (i < n) {
        if (text[i] == '-' && i + 1 < n
            && std::isdigit(static_cast<unsigned char>(text[i + 1]))) {
            const std::size_t start = i;
            i += 2;
            while (i < n && std::isdigit(static_cast<unsigned char>(text[i]))) {
                ++i;
            }
            if (i < n && text[i] == '.' && i + 1 < n
                && std::isdigit(static_cast<unsigned char>(text[i + 1]))) {
                i += 2;
                while (i < n
                       && std::isdigit(static_cast<unsigned char>(text[i]))) {
                    ++i;
                }
            }
            out.push_back(std::stod(text.substr(start, i - start)));
            continue;
        }
        if (std::isdigit(static_cast<unsigned char>(text[i]))) {
            const std::size_t start = i;
            ++i;
            while (i < n && std::isdigit(static_cast<unsigned char>(text[i]))) {
                ++i;
            }
            if (i < n && text[i] == '.' && i + 1 < n
                && std::isdigit(static_cast<unsigned char>(text[i + 1]))) {
                i += 2;
                while (i < n
                       && std::isdigit(static_cast<unsigned char>(text[i]))) {
                    ++i;
                }
            }
            out.push_back(std::stod(text.substr(start, i - start)));
            continue;
        }
        ++i;
    }
    return out;
}

namespace {

std::string trim_copy(const std::string& raw) {
    std::size_t a = 0;
    std::size_t b = raw.size();
    while (a < b && std::isspace(static_cast<unsigned char>(raw[a]))) {
        ++a;
    }
    while (b > a && std::isspace(static_cast<unsigned char>(raw[b - 1]))) {
        --b;
    }
    return raw.substr(a, b - a);
}

}  // namespace

Box4 footprint_bbox(const Sexpr& doc, int decimals) {
    if (decimals < 0) {
        throw std::runtime_error("footprint_bbox: decimals required");
    }
    if (!std::holds_alternative<SexprList>(doc.v)) {
        throw std::runtime_error("footprint_bbox: list required");
    }
    std::vector<double> xs;
    std::vector<double> ys;
    footprint_bbox_walk(std::get<SexprList>(doc.v), &xs, &ys);
    if (xs.empty()) {
        throw std::runtime_error("footprint_bbox: no measurable extent");
    }
    const auto [xmin, xmax] = std::minmax_element(xs.begin(), xs.end());
    const auto [ymin, ymax] = std::minmax_element(ys.begin(), ys.end());
    return Box4{py_round(*xmin, decimals), py_round(*ymin, decimals),
                py_round(*xmax, decimals), py_round(*ymax, decimals)};
}

SomOutline extract_som_scan(const std::string& text) {
    std::vector<std::pair<double, double>> edge_pts;
    std::unordered_map<std::string, std::tuple<double, double, double, double,
                                               double>>
        js_raw;
    bool in_gr = false;
    std::vector<std::pair<double, double>> gr_pts;
    bool in_fp = false;
    bool have_fp_at = false;
    double fp_x = 0.0;
    double fp_y = 0.0;
    double fp_rot = 0.0;
    std::string fp_ref;
    std::vector<double> pad_xs;
    std::vector<double> pad_ys;
    bool pad_pending = false;
    bool have_pad_at = false;
    double pad_at_x = 0.0;
    double pad_at_y = 0.0;

    auto commit_fp = [&]() {
        if (in_fp && (fp_ref == "J1" || fp_ref == "J2" || fp_ref == "J3")
            && have_fp_at && !pad_xs.empty()) {
            const auto [xmin, xmax] = std::minmax_element(pad_xs.begin(),
                                                          pad_xs.end());
            const auto [ymin, ymax] = std::minmax_element(pad_ys.begin(),
                                                          pad_ys.end());
            js_raw[fp_ref] = std::make_tuple(fp_x, fp_y, fp_rot, *xmax - *xmin,
                                             *ymax - *ymin);
        }
        in_fp = false;
    };

    std::size_t line_start = 0;
    while (line_start <= text.size()) {
        std::size_t line_end = text.find('\n', line_start);
        if (line_end == std::string::npos) {
            line_end = text.size();
        }
        const std::string raw = text.substr(line_start, line_end - line_start);
        if (line_end == text.size()) {
            line_start = text.size() + 1;
        } else {
            line_start = line_end + 1;
        }
        const std::string s = trim_copy(raw);
        if (s.rfind("(gr_line", 0) == 0 || s.rfind("(gr_arc", 0) == 0) {
            commit_fp();
            in_gr = true;
            gr_pts.clear();
            continue;
        }
        if (in_gr) {
            if (s.rfind("(start ", 0) == 0 || s.rfind("(mid ", 0) == 0
                || s.rfind("(end ", 0) == 0) {
                const auto vals = scan_floats(s);
                if (vals.size() >= 2) {
                    gr_pts.emplace_back(vals[0], vals[1]);
                }
            } else if (s.rfind("(layer ", 0) == 0) {
                if (s.find("\"Edge.Cuts\"") != std::string::npos) {
                    edge_pts.insert(edge_pts.end(), gr_pts.begin(),
                                    gr_pts.end());
                }
                in_gr = false;
            }
            continue;
        }
        if (s.rfind("(footprint ", 0) == 0) {
            commit_fp();
            in_fp = true;
            have_fp_at = false;
            fp_ref.clear();
            pad_xs.clear();
            pad_ys.clear();
            pad_pending = false;
            have_pad_at = false;
            continue;
        }
        if (!in_fp) {
            continue;
        }
        if (!have_fp_at && s.rfind("(at ", 0) == 0) {
            const auto vals = scan_floats(s);
            if (vals.size() < 2) {
                throw std::runtime_error("extract_som_scan: footprint at");
            }
            fp_x = vals[0];
            fp_y = vals[1];
            fp_rot = vals.size() > 2 ? vals[2] : 0.0;
            have_fp_at = true;
        } else if (s.rfind("(property \"Reference\"", 0) == 0) {
            std::vector<std::string> quotes;
            std::size_t q = 0;
            while (true) {
                const auto a = s.find('"', q);
                if (a == std::string::npos) {
                    break;
                }
                const auto b = s.find('"', a + 1);
                if (b == std::string::npos) {
                    break;
                }
                quotes.push_back(s.substr(a + 1, b - a - 1));
                q = b + 1;
            }
            if (quotes.size() >= 2) {
                fp_ref = quotes[1];
            }
        } else if (s.rfind("(pad ", 0) == 0) {
            pad_pending = true;
            have_pad_at = false;
        } else if (pad_pending && s.rfind("(at ", 0) == 0) {
            const auto vals = scan_floats(s);
            if (vals.size() < 2) {
                throw std::runtime_error("extract_som_scan: pad at");
            }
            pad_at_x = vals[0];
            pad_at_y = vals[1];
            have_pad_at = true;
        } else if (pad_pending && have_pad_at && s.rfind("(size ", 0) == 0) {
            const auto vals = scan_floats(s);
            if (vals.size() < 2) {
                throw std::runtime_error("extract_som_scan: pad size");
            }
            pad_xs.push_back(pad_at_x - vals[0] / 2.0);
            pad_xs.push_back(pad_at_x + vals[0] / 2.0);
            pad_ys.push_back(pad_at_y - vals[1] / 2.0);
            pad_ys.push_back(pad_at_y + vals[1] / 2.0);
            pad_pending = false;
        }
    }
    commit_fp();
    if (edge_pts.empty()) {
        throw std::runtime_error("extract_som_scan: Edge.Cuts required");
    }
    if (js_raw.find("J1") == js_raw.end() || js_raw.find("J2") == js_raw.end()
        || js_raw.find("J3") == js_raw.end()) {
        throw std::runtime_error("extract_som_scan: J1 J2 J3 required");
    }
    double x0 = edge_pts[0].first;
    double y0 = edge_pts[0].second;
    double x1 = x0;
    double y1 = y0;
    for (const auto& p : edge_pts) {
        x0 = std::min(x0, p.first);
        y0 = std::min(y0, p.second);
        x1 = std::max(x1, p.first);
        y1 = std::max(y1, p.second);
    }
    const double w = x1 - x0;
    const double h = y1 - y0;
    SomOutline out;
    out.w = py_round(w, 3);
    out.h = py_round(h, 3);
    for (const char* ref : {"J1", "J2", "J3"}) {
        const auto& row = js_raw[ref];
        const double px = std::get<0>(row);
        const double py = std::get<1>(row);
        const double rot = std::get<2>(row);
        const double pw = std::get<3>(row);
        const double ph = std::get<4>(row);
        const bool swap = std::fmod(rot, 180.0) == 90.0;
        const double ew = swap ? ph : pw;
        const double eh = swap ? pw : ph;
        SomJGeom j;
        j.ref = ref;
        j.pcb_x = px;
        j.pcb_y = py;
        j.rot = rot;
        j.x = py_round(w - (px - x0), 3);
        j.y = py_round(py - y0, 3);
        j.w = py_round(ew, 3);
        j.h = py_round(eh, 3);
        out.js.push_back(j);
    }
    return out;
}

std::vector<std::tuple<std::string, double, double, double, double>>
pad_boxes_named(
    const std::vector<std::tuple<std::string, double, double, double, double,
                                 double>>& rows,
    double rotation) {
    const double turn = rotation * (M_PI / 180.0);
    const double cs = std::cos(turn);
    const double sn = std::sin(turn);
    std::vector<std::tuple<std::string, double, double, double, double>> out;
    std::unordered_map<std::string, std::size_t> index;
    for (const auto& row : rows) {
        const std::string& name = std::get<0>(row);
        const double px = std::get<1>(row);
        const double py = std::get<2>(row);
        const double prot = std::get<3>(row) * (M_PI / 180.0);
        const double sw = std::get<4>(row);
        const double sh = std::get<5>(row);
        const double cx = px * cs + py * sn;
        const double cy = -px * sn + py * cs;
        const double tot = turn + prot;
        const double ct = std::fabs(std::cos(tot));
        const double st = std::fabs(std::sin(tot));
        const double hx = ct * sw / 2.0 + st * sh / 2.0;
        const double hy = st * sw / 2.0 + ct * sh / 2.0;
        Box4 box{cx - hx, cy - hy, cx + hx, cy + hy};
        const auto it = index.find(name);
        if (it == index.end()) {
            index[name] = out.size();
            out.emplace_back(name, box.x0, box.y0, box.x1, box.y1);
        } else {
            auto& hit = out[it->second];
            std::get<1>(hit) = std::min(std::get<1>(hit), box.x0);
            std::get<2>(hit) = std::min(std::get<2>(hit), box.y0);
            std::get<3>(hit) = std::max(std::get<3>(hit), box.x1);
            std::get<4>(hit) = std::max(std::get<4>(hit), box.y1);
        }
    }
    return out;
}

namespace {

bool word_char(unsigned char ch) {
    return (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z')
        || (ch >= '0' && ch <= '9') || ch == '_';
}

bool parse_py_plain(const std::string& text, std::size_t start, double* value,
                    std::size_t* after) {
    const std::size_t n = text.size();
    std::size_t i = start;
    if (i < n && text[i] == '-') {
        ++i;
    }
    if (i >= n || !std::isdigit(static_cast<unsigned char>(text[i]))) {
        return false;
    }
    ++i;
    while (i < n && std::isdigit(static_cast<unsigned char>(text[i]))) {
        ++i;
    }
    if (i < n && text[i] == '.' && i + 1 < n
        && std::isdigit(static_cast<unsigned char>(text[i + 1]))) {
        i += 2;
        while (i < n && std::isdigit(static_cast<unsigned char>(text[i]))) {
            ++i;
        }
    }
    *value = std::stod(text.substr(start, i - start));
    *after = i;
    return true;
}

bool match_fp_gfx(const std::string& text, std::size_t i, std::size_t* after) {
    static const char* tags[] = {"(fp_line", "(fp_rect", "(fp_poly",
                                 "(fp_circle", "(fp_arc"};
    for (const char* tag : tags) {
        const std::size_t len = std::char_traits<char>::length(tag);
        if (i + len <= text.size() && text.compare(i, len, tag) == 0) {
            if (i + len == text.size()
                || !word_char(static_cast<unsigned char>(text[i + len]))) {
                *after = i + len;
                return true;
            }
        }
    }
    return false;
}

void collect_coord_pair(const std::string& text, std::size_t begin,
                        std::size_t end, std::vector<double>* xs,
                        std::vector<double>* ys) {
    static const char* tags[] = {"start", "end", "mid", "xy", "center"};
    std::size_t i = begin;
    while (i < end) {
        if (text[i] != '(') {
            ++i;
            continue;
        }
        bool hit = false;
        std::size_t after_tag = 0;
        for (const char* tag : tags) {
            const std::size_t len = std::char_traits<char>::length(tag);
            if (i + 1 + len < end && text.compare(i + 1, len, tag) == 0
                && text[i + 1 + len] == ' ') {
                after_tag = i + 1 + len + 1;
                hit = true;
                break;
            }
        }
        if (!hit) {
            ++i;
            continue;
        }
        double x = 0.0;
        double y = 0.0;
        std::size_t after_x = 0;
        std::size_t after_y = 0;
        if (!parse_py_plain(text, after_tag, &x, &after_x)
            || after_x >= end || text[after_x] != ' '
            || !parse_py_plain(text, after_x + 1, &y, &after_y)
            || after_y >= end || text[after_y] != ')') {
            ++i;
            continue;
        }
        xs->push_back(x);
        ys->push_back(y);
        i = after_y + 1;
    }
}

}  // namespace

std::optional<std::pair<double, double>> courtyard_dims_from_text(
    const std::string& text) {
    std::vector<double> xs;
    std::vector<double> ys;
    const std::string layer = "(layer \"F.CrtYd\")";
    std::size_t i = 0;
    while (i < text.size()) {
        std::size_t after = 0;
        if (!match_fp_gfx(text, i, &after)) {
            ++i;
            continue;
        }
        const auto layer_at = text.find(layer, after);
        if (layer_at == std::string::npos) {
            break;
        }
        collect_coord_pair(text, after, layer_at, &xs, &ys);
        i = layer_at + layer.size();
    }
    if (xs.empty()) {
        i = 0;
        while (i < text.size()) {
            if (i + 5 > text.size() || text.compare(i, 5, "(pad ") != 0) {
                ++i;
                continue;
            }
            const auto nl = text.find('\n', i + 5);
            if (nl == std::string::npos) {
                break;
            }
            std::size_t j = nl + 1;
            while (j < text.size()
                   && std::isspace(static_cast<unsigned char>(text[j]))) {
                ++j;
            }
            if (j + 4 > text.size() || text.compare(j, 4, "(at ") != 0) {
                i = nl + 1;
                continue;
            }
            double x = 0.0;
            double y = 0.0;
            std::size_t after_x = 0;
            std::size_t after_y = 0;
            if (parse_py_plain(text, j + 4, &x, &after_x)
                && after_x < text.size() && text[after_x] == ' '
                && parse_py_plain(text, after_x + 1, &y, &after_y)) {
                xs.push_back(x);
                ys.push_back(y);
            }
            i = nl + 1;
        }
    }
    if (xs.empty()) {
        return std::nullopt;
    }
    const auto [xmin, xmax] = std::minmax_element(xs.begin(), xs.end());
    const auto [ymin, ymax] = std::minmax_element(ys.begin(), ys.end());
    return std::make_pair(py_round(*xmax - *xmin, 2),
                          py_round(*ymax - *ymin, 2));
}

std::vector<std::string> pad_names_from_text(const std::string& text) {
    std::vector<std::string> out;
    std::size_t i = 0;
    while (i < text.size()) {
        const auto pad = text.find("(pad", i);
        if (pad == std::string::npos) {
            break;
        }
        std::size_t j = pad + 4;
        if (j >= text.size()
            || !std::isspace(static_cast<unsigned char>(text[j]))) {
            i = pad + 4;
            continue;
        }
        while (j < text.size()
               && std::isspace(static_cast<unsigned char>(text[j]))) {
            ++j;
        }
        if (j >= text.size() || text[j] != '"') {
            i = j;
            continue;
        }
        const auto end = text.find('"', j + 1);
        if (end == std::string::npos) {
            break;
        }
        if (end > j + 1) {
            out.push_back(text.substr(j + 1, end - j - 1));
        }
        i = end + 1;
    }
    return out;
}

bool has_thru_pads_from_text(const std::string& text) {
    std::size_t i = 0;
    while (i < text.size()) {
        const auto pad = text.find("(pad", i);
        if (pad == std::string::npos) {
            return false;
        }
        std::size_t j = pad + 4;
        if (j >= text.size()
            || !std::isspace(static_cast<unsigned char>(text[j]))) {
            i = pad + 4;
            continue;
        }
        while (j < text.size()
               && std::isspace(static_cast<unsigned char>(text[j]))) {
            ++j;
        }
        if (j >= text.size() || text[j] != '"') {
            i = j;
            continue;
        }
        const auto end = text.find('"', j + 1);
        if (end == std::string::npos) {
            return false;
        }
        j = end + 1;
        if (j >= text.size()
            || !std::isspace(static_cast<unsigned char>(text[j]))) {
            i = end + 1;
            continue;
        }
        while (j < text.size()
               && std::isspace(static_cast<unsigned char>(text[j]))) {
            ++j;
        }
        if ((j + 9 <= text.size() && text.compare(j, 9, "thru_hole") == 0
             && (j + 9 == text.size()
                 || !word_char(static_cast<unsigned char>(text[j + 9]))))
            || (j + 12 <= text.size()
                && text.compare(j, 12, "np_thru_hole") == 0
                && (j + 12 == text.size()
                    || !word_char(
                        static_cast<unsigned char>(text[j + 12]))))) {
            return true;
        }
        i = end + 1;
    }
    return false;
}

std::vector<std::tuple<std::string, std::string, double, double, double, double,
                       double>>
scan_pad_nodes(const Sexpr& doc) {
    std::vector<std::tuple<std::string, std::string, double, double, double,
                           double, double>>
        out;
    if (!std::holds_alternative<SexprList>(doc.v)) {
        return out;
    }
    for (const Sexpr& child : std::get<SexprList>(doc.v)) {
        if (!is_tagged_list(child, "pad")) {
            continue;
        }
        const SexprList& lst = std::get<SexprList>(child.v);
        std::string name;
        std::string ptype;
        if (lst.size() > 1) {
            try {
                name = py_str(lst[1]);
            } catch (const std::runtime_error&) {
                name.clear();
            }
        }
        if (lst.size() > 2) {
            try {
                ptype = py_str(lst[2]);
            } catch (const std::runtime_error&) {
                ptype.clear();
            }
        }
        const SexprList* at = find_tagged_child(lst, "at");
        if (at == nullptr || at->size() < 3 || !is_number((*at)[1])
            || !is_number((*at)[2])) {
            continue;
        }
        double prot = 0.0;
        if (at->size() > 3 && is_number((*at)[3])) {
            prot = std::get<double>((*at)[3].v);
        }
        double sw = 0.0;
        double sh = 0.0;
        const SexprList* size = find_tagged_child(lst, "size");
        if (size != nullptr && size->size() >= 3 && is_number((*size)[1])
            && is_number((*size)[2])) {
            sw = std::get<double>((*size)[1].v);
            sh = std::get<double>((*size)[2].v);
        }
        out.emplace_back(name, ptype, std::get<double>((*at)[1].v),
                         std::get<double>((*at)[2].v), prot, sw, sh);
    }
    return out;
}

double font_size(const Sexpr& node, double default_size) {
    if (!std::holds_alternative<SexprList>(node.v)) {
        return default_size;
    }
    return font_size_of(std::get<SexprList>(node.v), default_size);
}

std::vector<std::tuple<std::string, double, double>> inst_pad_xy(
    const std::vector<std::tuple<std::string, double, double>>& pads,
    double inst_x, double inst_y, double rotation, int decimals) {
    std::vector<std::tuple<std::string, double, double>> out;
    out.reserve(pads.size());
    for (const auto& pad : pads) {
        const auto turned =
            turn_point(std::get<1>(pad), std::get<2>(pad), rotation);
        out.emplace_back(std::get<0>(pad),
                         py_round(inst_x + turned.first, decimals),
                         py_round(inst_y + turned.second, decimals));
    }
    return out;
}

std::vector<Box4> collect_emitted_text_boxes(const Sexpr& doc,
                                             bool include_silk_gfx,
                                             double default_size) {
    std::vector<Box4> boxes;
    if (!std::holds_alternative<SexprList>(doc.v)) {
        return boxes;
    }
    for (const Sexpr& node : std::get<SexprList>(doc.v)) {
        if (!std::holds_alternative<SexprList>(node.v)) {
            continue;
        }
        const SexprList& lst = std::get<SexprList>(node.v);
        if (lst.empty()) {
            continue;
        }
        std::string head;
        try {
            head = py_str(lst[0]);
        } catch (const std::runtime_error&) {
            continue;
        }
        if (head == "gr_text" && lst.size() >= 2
            && std::holds_alternative<std::string>(lst[1].v)) {
            const SexprList* at = find_tagged_child(lst, "at");
            if (at != nullptr && at->size() >= 3 && is_number((*at)[1])
                && is_number((*at)[2])) {
                boxes.push_back(text_box(std::get<std::string>(lst[1].v),
                                         std::get<double>((*at)[1].v),
                                         std::get<double>((*at)[2].v),
                                         font_size_of(lst, default_size),
                                         0.15));
            }
            continue;
        }
        if (head != "footprint") {
            continue;
        }
        const SexprList* fat = find_tagged_child(lst, "at");
        if (fat == nullptr || fat->size() < 3 || !is_number((*fat)[1])
            || !is_number((*fat)[2])) {
            continue;
        }
        const double fx = std::get<double>((*fat)[1].v);
        const double fy = std::get<double>((*fat)[2].v);
        double frot = 0.0;
        if (fat->size() > 3 && is_number((*fat)[3])) {
            frot = std::get<double>((*fat)[3].v);
        }
        const double angle = frot * (M_PI / 180.0);
        const double ca = std::cos(angle);
        const double sa = std::sin(angle);
        if (include_silk_gfx) {
            for (const Sexpr& child : lst) {
                if (!std::holds_alternative<SexprList>(child.v)) {
                    continue;
                }
                const SexprList& c = std::get<SexprList>(child.v);
                if (c.empty()) {
                    continue;
                }
                try {
                    if (!is_gfx_geom(c[0])) {
                        continue;
                    }
                } catch (const std::runtime_error&) {
                    continue;
                }
                const SexprList* lyr = find_tagged_child(c, "layer");
                if (lyr == nullptr || lyr->size() < 2
                    || py_str((*lyr)[1]) != "F.SilkS") {
                    continue;
                }
                auto pts_hw = silk_gfx_pts(child);
                auto hit = silk_gfx_extent(pts_hw.first, fx, fy, ca, sa,
                                           pts_hw.second);
                if (hit.has_value()) {
                    boxes.push_back(*hit);
                }
            }
        }
        for (const Sexpr& child : lst) {
            if (!std::holds_alternative<SexprList>(child.v)) {
                continue;
            }
            const SexprList& c = std::get<SexprList>(child.v);
            if (c.empty()) {
                continue;
            }
            std::string tag;
            try {
                tag = py_str(c[0]);
            } catch (const std::runtime_error&) {
                continue;
            }
            std::string txt;
            bool have_txt = false;
            if (tag == "fp_text" && c.size() > 2) {
                std::string kind;
                if (std::holds_alternative<Sexpr::Sym>(c[1].v)) {
                    kind = std::get<Sexpr::Sym>(c[1].v).name;
                }
                if (kind != "reference" && kind != "value") {
                    continue;
                }
                if (std::holds_alternative<std::string>(c[2].v)) {
                    txt = std::get<std::string>(c[2].v);
                    have_txt = true;
                }
            } else if (tag == "property" && c.size() > 2) {
                std::string name;
                if (std::holds_alternative<std::string>(c[1].v)) {
                    name = std::get<std::string>(c[1].v);
                }
                if (name != "Reference" && name != "Value") {
                    continue;
                }
                const SexprList* lyr = find_tagged_child(c, "layer");
                if (lyr == nullptr || lyr->size() < 2
                    || py_str((*lyr)[1]) != "F.SilkS") {
                    continue;
                }
                if (std::holds_alternative<std::string>(c[2].v)) {
                    txt = std::get<std::string>(c[2].v);
                    have_txt = true;
                }
            } else {
                continue;
            }
            const SexprList* hide = find_tagged_child(c, "hide");
            if (hide != nullptr
                && (hide->size() < 2 || py_str((*hide)[1]) == "yes")) {
                continue;
            }
            const SexprList* lat = find_tagged_child(c, "at");
            if (lat == nullptr || lat->size() < 3 || !is_number((*lat)[1])
                || !is_number((*lat)[2]) || !have_txt) {
                continue;
            }
            const double lx = std::get<double>((*lat)[1].v);
            const double ly = std::get<double>((*lat)[2].v);
            boxes.push_back(text_box(txt, fx + lx * ca + ly * sa,
                                     fy - lx * sa + ly * ca,
                                     font_size_of(c, default_size), 0.15));
        }
    }
    return boxes;
}

}  // namespace schgen
