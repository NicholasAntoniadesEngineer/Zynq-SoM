#pragma once

#include "schgen/seat.hpp"
#include "schgen/sexpr.hpp"

#include <optional>
#include <string>
#include <tuple>
#include <unordered_map>
#include <utility>
#include <vector>

namespace schgen {

std::vector<std::tuple<int, int, std::string>> thermal_via_scan(
    const Sexpr& footprint,
    const std::unordered_map<std::string, std::pair<int, std::string>>&
        pad_nets);

std::pair<std::vector<std::pair<double, double>>, double> silk_gfx_pts(
    const Sexpr& node);

std::pair<std::vector<Box4>, std::vector<Box4>> collect_fp_silk_gfx(
    const Sexpr& footprint);

double farm_row_right_bound(double extent_x0, double extent_x1_flow,
                            double a3_center_x, double titleblock_left,
                            double titleblock_margin, double cap_pitch);

std::vector<std::string> conn_port_columns(const std::vector<double>& ys,
                                           double row_pitch, double eps);

std::vector<std::vector<int>> conn_cluster_groups(
    const std::vector<double>& ys, double row_pitch, double eps);

std::vector<std::tuple<std::string, double, double, double, double>>
pad_boxes_local(
    const std::vector<std::tuple<std::string, double, double, double, double,
                                 double>>& rows,
    double rotation);

Box4 inst_placed_box(const Box4& local_bbox, double inst_x, double inst_y,
                     double rotation, int decimals);

std::vector<Box4> collect_gr_text_boxes(const Sexpr& doc, double default_size);

struct RefdesProp {
    int footprint_index = -1;
    int property_index = -1;
    std::string ref;
    double fp_x = 0.0;
    double fp_y = 0.0;
    double cos_a = 0.0;
    double sin_a = 0.0;
    double local_x = 0.0;
    double local_y = 0.0;
    double size = 0.0;
    bool bottom = false;
    Box4 text_box;
};

std::vector<RefdesProp> collect_refdes_props(const Sexpr& doc,
                                             double default_size);

std::string footprint_alias(
    const std::string& footprint,
    const std::vector<std::pair<std::string, std::string>>& aliases);

bool mirror_assert_ok(bool mirror, const std::string& side,
                      bool mirrored_path);

bool needs_flag(const std::vector<std::string>& pin_etypes,
                const std::vector<std::string>& driver_etypes);

std::tuple<double, double, double, double> farm_cluster_origin(
    double extent_x0, double extent_y1, double unit, int n_box_bucks);

double next_rail_col(double col_x, double cap_pitch, double prev_rail_w,
                     double rail_w, double unit, double extra);

Sexpr set_font_size(Sexpr prop, double size);

std::pair<Sexpr, int> hide_undersom_bottom_refs(
    Sexpr doc, double x0, double y0, double x1, double y1);

Box4 footprint_bbox(const Sexpr& doc, int decimals);

struct SomJGeom {
    std::string ref;
    double pcb_x = 0.0;
    double pcb_y = 0.0;
    double rot = 0.0;
    double x = 0.0;
    double y = 0.0;
    double w = 0.0;
    double h = 0.0;
};

struct SomOutline {
    double w = 0.0;
    double h = 0.0;
    std::vector<SomJGeom> js;
};

SomOutline extract_som_scan(const std::string& text);

std::vector<std::tuple<std::string, double, double, double, double>>
pad_boxes_named(
    const std::vector<std::tuple<std::string, double, double, double, double,
                                 double>>& rows,
    double rotation);

std::optional<std::pair<double, double>> courtyard_dims_from_text(
    const std::string& text);

std::vector<std::string> pad_names_from_text(const std::string& text);

bool has_thru_pads_from_text(const std::string& text);

std::vector<std::tuple<std::string, std::string, double, double, double, double,
                       double>>
scan_pad_nodes(const Sexpr& doc);

}  // namespace schgen
