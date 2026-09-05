#pragma once

#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "schgen/seat.hpp"

namespace schgen {

struct NearRectGap {
    double gap = 0.0;
    int index = -1;
};

std::pair<double, double> dodge_value_off_nc(
    const std::string& text, double vp_x, double vp_y, double ax, double ay,
    double unit, double char_w, double line_h, double size,
    const std::vector<Box4>& nc_boxes, double nc_pad);

bool vband_stem_free(double x, double y0, double y1,
                     const std::vector<Box4>& segs, double pad);

std::optional<double> lane_x(int sgn, double y0, double y1, double start,
                             double unit, double half_w, double y_pad,
                             double spot_pad, const std::vector<Box4>& parts,
                             const std::vector<Box4>& segs,
                             const std::vector<Box4>& ncs);

bool foreign_rows_clear(const Box4& box,
                        const std::vector<double>& foreign_ys, double eps);

double cell_floor(double x0, double x1, const std::vector<Box4>& boxes,
                  const std::vector<Box4>& segs);

NearRectGap nearest_rect_gap(const Box4& subject,
                             const std::vector<Box4>& others,
                             double touch_eps);

Box4 body_box(double x0, double y0, double x1, double y1, double ax,
              double ay, int rot);
Box4 boxes_paths_extent(const std::vector<Box4>& boxes,
                        const std::vector<std::pair<double, double>>& pts);
double band_edge(double y0, double y1, int side, double default_edge,
                 const std::vector<Box4>& boxes,
                 const std::vector<Box4>& segs);
std::optional<double> lane_in_dir(
    int sgn, double pt_x, double pt_y, double ty, double unit, double half_w,
    double y_pad, double spot_pad, double corridor_pad, double x_nudge,
    const std::vector<Box4>& parts, const std::vector<Box4>& spot_segs,
    const std::vector<Box4>& ncs, const std::vector<Box4>& corridor_boxes,
    const std::vector<Seg2>& corridor_segs);

struct OwnedBox {
    Box4 box;
    std::string owner;
    std::string kind;
};

struct PinTextIn {
    double x = 0.0;
    double y = 0.0;
    int rotation = 0;
    double length = 0.0;
    bool hidden = false;
    std::string number;
    std::string name;
};

struct LabeledBox {
    Box4 box;
    std::string kind;
};

using EscapeLeg = std::pair<std::pair<double, double>, std::pair<double, double>>;

std::vector<EscapeLeg> escape_run_legs(
    double px, double py, double tx, double unit, double edge_clear,
    const std::vector<OwnedBox>& boxes, const std::vector<Box4>& parts,
    const std::vector<Box4>& spot_segs, const std::vector<Box4>& ncs,
    const std::vector<Box4>& corridor_boxes,
    const std::vector<Seg2>& corridor_segs, const std::vector<Box4>& stem_segs,
    double spot_pad, double corridor_pad, double stem_pad);

std::vector<LabeledBox> pin_text_boxes(
    const std::vector<PinTextIn>& pins, double part_x, double part_y,
    int part_rot, bool pin_numbers_hidden, bool pin_names_hidden,
    double char_w, double line_h, double size);

std::optional<std::vector<std::pair<double, double>>> bfs_escape(
    double pt_x, double pt_y, double ty, double unit, double extent_x0,
    double extent_y0, double extent_x1, double extent_y1, double margin_cells,
    const std::vector<Box4>& boxes, const std::vector<Seg2>& segs,
    double cell_pad);

}  // namespace schgen
