#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <tuple>
#include <unordered_map>
#include <utility>
#include <vector>

#include "schgen/occupancy.hpp"
#include "schgen/seat.hpp"

namespace schgen {

struct ShelfItem {
    std::string ref;
    Box4 halo;
    double extra = 0.0;
    bool is_cp = false;
};

struct ShelfOcc {
    Box4 box;
    double extra = 0.0;
    bool is_cp = false;
};

struct ShelfPacked {
    std::vector<std::tuple<std::string, double, double>> placed;
    double packed_w = 0.0;
    double packed_h = 0.0;
};

ShelfPacked shelf_pack(const std::vector<ShelfItem>& items, double target_w,
                       const std::vector<ShelfOcc>& blockers, double zone_pad);

struct ViaObstacle {
    double cx = 0.0;
    double cy = 0.0;
    double hx = 0.0;
    double hy = 0.0;
    std::string nname;
    double drill = 0.0;
    std::string label;
};

struct ViaSiteSpec {
    double origin_x = 0.0;
    double origin_y = 0.0;
    double board_w = 0.0;
    double board_h = 0.0;
    double edge = 0.0;
    double via_size = 0.0;
    double via_drill = 0.0;
    double via_clear = 0.0;
    double hole_samenet = 0.0;
    double via_h2h = 0.0;
    double via_spacing = 0.0;
};

struct ViaBlockHit {
    bool blocked = false;
    std::string kind;
    std::string label;
    std::string nname;
    double x = 0.0;
    double y = 0.0;
};

ViaBlockHit via_site_blocker(
    double vx, double vy, const ViaSiteSpec& spec,
    const std::vector<ViaObstacle>& obstacles,
    const std::vector<std::pair<double, double>>& chosen);

std::vector<std::pair<double, double>> fallback_via_sites(
    double x0, double y0, double x1, double y1, double via_size,
    double pitch);

double overlap_area(const Box4& a, const Box4& b);
Box4 text_box(const std::string& txt, double x, double y, double size,
              double margin);
double point_box_dist(double x, double y, const Box4& box);
double seg_box_dist(double x1, double y1, double x2, double y2,
                    const Box4& box);
std::vector<std::vector<std::pair<double, std::string>>> band_cover(
    const std::vector<std::pair<double, std::string>>& points, double reach);
std::pair<bool, double> coverage_ok(
    double u, double v, const std::vector<std::pair<double, double>>& members,
    double bound);
bool point_on_seg(double px, double py, double x0, double y0, double x1,
                  double y1, bool interior_only);

class SilkBoxIndex {
public:
    explicit SilkBoxIndex(double cell);
    void add(const Box4& box);
    double pen(const Box4& gb) const;
    bool hits(const Box4& gb) const;
    const std::vector<Box4>& boxes() const { return boxes_; }

private:
    int cell_of(double value) const;
    std::uint64_t key(int gx, int gy) const;
    std::vector<int> near(const Box4& box) const;

    double cell_ = 8.0;
    std::vector<Box4> boxes_;
    std::unordered_map<std::uint64_t, std::vector<int>> cells_;
};

class BreatheGrid {
public:
    BreatheGrid(double board_w, double board_h, double cell, double origin_x,
                double origin_y);
    void stamp(const Box4& box, int val);
    bool free(const Box4& box) const;

private:
    int nx_ = 0;
    int ny_ = 0;
    double cell_ = 0.0;
    double origin_x_ = 0.0;
    double origin_y_ = 0.0;
    std::vector<std::uint8_t> cells_;
};

struct ClearLabel {
    double x = 0.0;
    double y = 0.0;
    Box4 box;
    double extra = 0.0;
};

ClearLabel place_clear_label(double cx0, double cy0, double cx1, double cy1,
                             const std::string& label, double size,
                             const SilkBoxIndex& occupied,
                             const SilkBoxIndex* placed,
                             const std::optional<Box4>& bounds);
bool segments_cross(double ax0, double ay0, double ax1, double ay1,
                    double bx0, double by0, double bx1, double by1);
std::optional<Box4> boxes_union(const std::vector<Box4>& boxes);
std::pair<double, double> text_wh(const std::string& text, double size,
                                  double char_w, double line_h);
Box4 centered_box(const std::string& text, double cx, double cy, double size,
                  double char_w, double line_h, bool vertical);
Box4 llabel_box(const std::string& text, double x, double y, int rotation,
                double size, double char_w, double line_h, double width_pad,
                double gap);
std::optional<Box4> silk_gfx_extent(
    const std::vector<std::pair<double, double>>& pts, double fx, double fy,
    double ca, double sa, double hw);
double pair_gap(const Halo& a_reach, const Halo& a_inset, const Halo& b_reach,
                const Halo& b_inset, char axis, double floor);

Box4 glabel_box(const std::string& text, double x, double y, int rotation,
                double size, double char_w, double line_h, double pad_len,
                double glabel_h, double inset);

std::pair<Halo, Halo> zone_fanout_reach(
    double zw, double zh,
    const std::vector<std::tuple<double, double, double, double, int, double>>&
        members,
    int min_subject_pins);

std::vector<Comp> edge_components(char edge, double block_x, double block_y,
                                  double board_w, double board_h,
                                  int punch_mask,
                                  const std::vector<Comp>& comps);
std::tuple<double, double, int, int> som_decoupling_grid(double som_w,
                                                         double som_h, int n,
                                                         double inset);
std::vector<std::pair<double, double>> som_decoupling_cells(
    double som_x, double som_y, double som_w, double som_h, int n,
    double inset);
std::vector<Comp> som_components(
    double origin_x, double origin_y, double radius,
    const std::vector<std::pair<double, double>>& cells,
    const std::vector<Box4>& bands, int bottom_mask, int punch_mask);
bool any_boxes_overlap(const std::vector<Box4>& boxes, double halo);
std::vector<int> pack_interior_order(const std::vector<std::string>& names,
                                     const std::vector<int>& tiers,
                                     const std::vector<double>& conn,
                                     const std::vector<double>& area);
double pack_conn_weight(const std::vector<double>& aff_weights,
                        double som_pull);
std::vector<std::pair<std::string, std::vector<std::string>>> nets_by_sheet(
    const std::vector<std::pair<std::string, std::vector<std::string>>>&
        net_sheets);
int obstacle_bucket(double region_u0, double region_v0, double region_u1,
                    double region_v1, double box_u0, double box_v0,
                    double box_u1, double box_v1, bool same_ref, bool net_gnd,
                    bool side_top);
std::tuple<double, double, double> obstacle_hole(double box_u0, double box_v0,
                                                 double box_u1, double box_v1);
double net_clearance_rule(bool power);
std::vector<std::pair<double, double>> cout_column_centers(
    const Box4& inductor_out, double pad, double cout_gap,
    double template_clear, const std::vector<std::pair<double, double>>& halves);
std::pair<double, double> bulk_cap_pose(
    double hf_ox, const Box4& hf_box, const std::string& direction, double gap,
    double hx, double hy, double inductor_left, double template_clear);

struct RefdesMove {
    bool moved = false;
    double local_x = 0.0;
    double local_y = 0.0;
    double size = 0.0;
    Box4 add_box;
};

RefdesMove place_refdes(
    const Box4& court, const std::string& ref, double size, const Box4& box,
    const SilkBoxIndex& occupied, const SilkBoxIndex& placed,
    const Box4& bounds, double fx, double fy, double ca, double sa,
    double min_size, double box_pad, double far_off, double pen_eps,
    double off_improve, const std::vector<double>& shrinks);

std::vector<Box4> som_keepout_rects(
    double som_x, double som_y, double som_w, double som_h, double occ_pad,
    const std::vector<std::tuple<double, double, double, double>>& connectors,
    double seat_band);

std::vector<Comp> zone_components_assemble(
    const std::vector<Box4>& minor_boxes, const std::vector<Box4>& punch_boxes,
    int minor_mask, int punch_mask);

std::pair<double, double> part_dims_from_name(
    const std::string& name,
    const std::vector<std::tuple<std::string, double, double>>& fixed_dims,
    double default_w, double default_h);

std::string ref_prefix(const std::string& ref);

bool is_testpoint_ref(const std::string& ref);

bool is_cluster_passive(
    const std::string& ref, int pins,
    const std::vector<std::string>& not_plain,
    const std::vector<std::string>& prefixes);

std::pair<double, std::string> intelligent_need(
    int pins,
    const std::vector<std::tuple<int, double, std::string>>& tiers,
    double top_need, const std::string& top_basis);

std::vector<std::tuple<double, double, double, double, int, double>>
zone_fanout_members_rows(
    const std::vector<std::tuple<double, double, double, double, double, double,
                                 double, int>>& rows,
    int min_subject_pins,
    const std::vector<std::tuple<int, double>>& need_tiers, double top_need);

struct ReorderAssign {
    int before = 0;
    int best = 0;
    std::vector<int> assign;
};

ReorderAssign reorder_cluster_assign(
    const std::vector<std::vector<std::vector<Seg2>>>& segs,
    const std::vector<int>& assign0, int sweeps);

bool visual_hv_cross(double ax0, double ay0, double ax1, double ay1,
                     double bx0, double by0, double bx1, double by1);
bool collinear_overlap(double ax0, double ay0, double ax1, double ay1,
                       double bx0, double by0, double bx1, double by1);

Box4 som_core_rect(double som_x, double som_y, double som_w, double som_h,
                   double origin_x, double origin_y, double clearance);

std::vector<std::tuple<std::string, double, double>> rotate_offsets_90(
    const std::vector<std::tuple<std::string, double, double>>& offs,
    double zone_w);

std::vector<std::tuple<std::string, std::vector<std::string>>>
cluster_interchangeable_rows(
    const std::vector<std::tuple<std::string, double, double>>& members,
    double tol_x, double tol_y);

std::pair<double, double> nearest_manhattan(
    double px, double py, const std::vector<std::pair<double, double>>& pts);

double overlap_1d(double a0, double a1, double b0, double b1);

std::optional<std::pair<std::string, double>> same_edge_gap(
    const Box4& a, const Box4& b, double band_frac);

std::optional<std::pair<double, double>> foreign_t_touch(
    double ax0, double ay0, double ax1, double ay1, double bx0, double by0,
    double bx1, double by1, bool same_net);

std::tuple<double, double, double, double, double, double> refdes_hit_court(
    double fx, double fy, double ca, double sa, double lx, double ly,
    const std::optional<Box4>& court);

std::pair<double, double> uv_to_board(double cx, double cy, double u, double v,
                                      double rot);
std::pair<double, double> board_to_uv(double cx, double cy, double bx,
                                      double by, double rot);

Box4 corridor_local_from_uv(
    const std::vector<std::pair<double, double>>& pads, double r_construct,
    double v_margin);

Box4 corridor_board_rect(const Box4& local, double cx, double cy, double rot);

std::pair<double, double> mirror_offset_x(double ox, double oy, const Box4& cb,
                                          double zone_w);

Box4 offset_turned_box(const Box4& bbox, double rot, double ox, double oy);
std::vector<Box4> offset_boxes(const std::vector<Box4>& boxes, double ox,
                               double oy);

struct GridControls {
    std::vector<std::tuple<std::string, double, double>> offs;
    std::vector<Box4> occ;
    double packed_w = 0.0;
    double packed_h = 0.0;
};

GridControls grid_controls(
    const std::vector<std::tuple<std::string, double, double, double, double>>&
        items,
    double target_w, double button_gap, double zone_pad, double place_clear);

struct ContactGeom {
    double row_v = 0.0;
    double half_w = 0.0;
    double half_h = 0.0;
    double span_u = 0.0;
    double pitch = 0.0;
};

ContactGeom contact_geometry(
    const std::vector<std::tuple<double, double, double, double>>& pads);

struct ViaClear {
    double margin = 0.0;
    double hole_foreign = 0.0;
    double hole_samenet = 0.0;
    double hole_hole = 0.0;
};

std::pair<bool, std::string> via_feasible(
    double u, double v, double dia, double drill,
    const std::vector<std::tuple<double, double, double, double, double,
                                 std::string>>& front_cu,
    const std::vector<std::tuple<double, double, double, double, double,
                                 std::string>>& back_cu,
    const std::vector<std::tuple<double, double, double, double, double,
                                 std::string>>& samenet,
    const std::vector<std::tuple<double, double, double, std::string>>& holes,
    const ViaClear& clear, bool want_audit);

struct SeatVia {
    double u = 0.0;
    double v = 0.0;
    double dia = 0.0;
    double drill = 0.0;
    double worst = 0.0;
    std::vector<std::string> members;
};

struct SeatLedger {
    std::string kind;
    std::string conn;
    double u = 0.0;
    double v = 0.0;
    double dia = 0.0;
    double drill = 0.0;
    double worst = 0.0;
    double at = 0.0;
    int depth = 0;
    std::vector<std::string> members;
};

struct SeatBandResult {
    std::vector<SeatVia> vias;
    std::vector<SeatLedger> ledger;
    std::vector<std::string> audit;
};

SeatBandResult seat_band(
    const std::vector<std::tuple<std::string, double, double>>& members,
    const std::vector<std::tuple<double, double, double, double, double,
                                 std::string>>& front_cu,
    const std::vector<std::tuple<double, double, double, double, double,
                                 std::string>>& back_cu,
    const std::vector<std::tuple<double, double, double, double, double,
                                 std::string>>& samenet,
    const std::vector<std::tuple<double, double, double, std::string>>& holes,
    double row_v, double half_h,
    const std::vector<std::pair<double, double>>& ladder, const ViaClear& clear,
    double via_row, double r_construct, double lattice, const std::string& conn,
    int depth);

bool is_passive_ref(const std::string& ref);

std::string classify_side(const std::string& ref, const std::string& lib,
                          const Box4& bbox, bool in_decoupling, bool two_side,
                          double top_area,
                          const std::vector<std::string>& top_always);

std::vector<std::string> decoupling_caps(
    const std::vector<std::tuple<std::string, std::vector<std::string>>>&
        net_refs);

double zone_target_w(double tot_area, double fill, double aspect,
                     double floor_mm);

double connector_target_w(double row_span, double zone_pad, double tot_area,
                          double fill, double aspect);

Box4 canonical_plane_rect(double origin_x, double origin_y, double board_w,
                          double board_h, double edge_back);

Box4 isolation_void_rect(const Box4& court, double margin);

Box4 board_box_to_uv(double cx, double cy, double rot, const Box4& box);

struct EscapeLadderSeg {
    double ax = 0.0;
    double ay = 0.0;
    double bx = 0.0;
    double by = 0.0;
    double w = 0.0;
    std::string role;
};

struct EscapeLadderCheck {
    int via_seg_components = 0;
    int pad_stubs = 0;
};

EscapeLadderCheck escape_ladder_connected(
    const std::vector<std::tuple<double, double, double>>& vias,
    const std::vector<std::tuple<double, double, double, double, double,
                                 std::string>>& segs,
    const std::vector<std::pair<double, double>>& pads, double half_w,
    double half_h);

std::optional<double> escape_redundancy_u(
    double base_u, double base_v, double dia, double drill,
    const std::vector<std::tuple<double, double, double, double, double,
                                 std::string>>& front_cu,
    const std::vector<std::tuple<double, double, double, double, double,
                                 std::string>>& back_cu,
    const std::vector<std::tuple<double, double, double, double, double,
                                 std::string>>& samenet,
    const std::vector<std::tuple<double, double, double, std::string>>& holes,
    const ViaClear& clear, double redundancy_offset, double lattice,
    int max_steps);

std::vector<EscapeLadderSeg> escape_ladder_plan(
    const std::vector<std::tuple<double, double, std::string>>& gnd_pads,
    const std::vector<std::pair<double, double>>& vias, double pitch,
    double pitch_tol, double row_v, double stub_w_pair,
    double stub_w_single, double spine_w);

bool via_in_escape_region(double bx, double by, const Box4& zone,
                          double margin);
bool coexistence_box_hit(double inst_x, double inst_y, double rot,
                         const Box4& box, double region_u, double region_v);
Box4 legalize_som_rect(double som_x, double som_y, double som_w, double som_h,
                       double pad);
std::vector<Box4> legalize_mh_corners(double board_w, double board_h,
                                      double mh_ko);
std::vector<std::tuple<std::string, double, double, double, double>>
som_jack_rects(
    double som_x, double som_y,
    const std::vector<std::tuple<std::string, double, double, double, double>>&
        jacks);
Box4 grow_rect(const Box4& box, double margin);
Box4 offset_rect(const Box4& box, double dx, double dy);
bool rect_covers(const Box4& outer, const Box4& inner);
bool rects_intersect_open(const Box4& a, const Box4& b);
bool point_in_rect(double x, double y, const Box4& box);
std::pair<double, double> rect_center(const Box4& box);
std::pair<double, double> coexistence_region(double span_u, double row_v,
                                             double half_h, double lane_handle,
                                             double margin);
double construct_reach(double r_construct, double row_v);
Box4 obstacle_scan_region(const std::vector<double>& us, double margin);
std::pair<double, double> escape_lane_extents(double row_v, double half_h,
                                              double lane_handle);
Box4 aabb_from_corners(double x0, double y0, double x1, double y1, int digits);
double min_hypot_to_points(
    double u, double v,
    const std::vector<std::pair<double, double>>& pts);

std::vector<std::vector<Seg2>> cluster_slot_segs(
    const std::vector<std::tuple<std::string, double, double>>& pad_offs,
    const std::vector<std::string>& pad_nets,
    const std::vector<std::pair<double, double>>& slots,
    const std::vector<std::tuple<std::string, std::vector<std::pair<double, double>>>>&
        static_pts);

}  // namespace schgen
