#pragma once

#include "schgen/seat.hpp"
#include "schgen/sexpr.hpp"

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

}  // namespace schgen
