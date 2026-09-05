#pragma once

#include <utility>
#include <vector>

namespace schgen {

struct Box4 {
    double x0 = 0.0;
    double y0 = 0.0;
    double x1 = 0.0;
    double y1 = 0.0;
};

struct AlignTerm {
    double rxc = 0.0;
    double ryc = 0.0;
    std::vector<std::pair<double, double>> pts;
};

struct BoundGroup {
    std::vector<Box4> boxes;
    double limit = 0.0;
};

struct Subject {
    Box4 box;
    double need = 0.0;
};

struct SeatHit {
    double score = 0.0;
    double abs_x = 0.0;
    double abs_y = 0.0;
    double rot = 0.0;
    double cx = 0.0;
    double cy = 0.0;
};

struct SeatList {
    std::vector<SeatHit> hits;
    bool truncated = false;
};

struct CandHit {
    double dist = 0.0;
    double abs_x = 0.0;
    double abs_y = 0.0;
    double rot = 0.0;
    double cx = 0.0;
    double cy = 0.0;
    Box4 body{};
};

struct CandList {
    std::vector<CandHit> hits;
    bool truncated = false;
};

struct DfsResult {
    bool solved = false;
    bool budget_hit = false;
    int nodes = 0;
    std::vector<int> pick;
};

struct Seg2 {
    double x0 = 0.0;
    double y0 = 0.0;
    double x1 = 0.0;
    double y1 = 0.0;
};

bool boxes_overlap(const Box4& a, const Box4& b, double halo);
double box_gap(const Box4& a, const Box4& b);
bool spot_free(const Box4& bx, double pad,
               const std::vector<Box4>& parts,
               const std::vector<Box4>& segs,
               const std::vector<Box4>& ncs);
bool corridor_free(double y, double xa, double xb,
                   const std::vector<Box4>& boxes,
                   const std::vector<Seg2>& segs, double seg_pad);
bool corridor_clear_vert(double x, double y_pin, double ty,
                         const std::vector<Box4>& boxes,
                         const std::vector<Seg2>& segs, double seg_pad);
bool cell_free_point(double x, double y,
                     const std::vector<Box4>& boxes,
                     const std::vector<Seg2>& segs, double seg_pad);

SeatList seat_scan(
    double tcx, double tcy, int n, double step, double halo, double net_w,
    int cap,
    const std::vector<Box4>& placed,
    const std::vector<Box4>& forbid,
    const std::vector<Subject>& subjects,
    const std::vector<BoundGroup>& attract,
    const std::vector<BoundGroup>& repulse,
    const std::vector<double>& rots,
    const std::vector<std::vector<Box4>>& rel_pads,
    const std::vector<Box4>& body,
    const std::vector<std::vector<AlignTerm>>& align);

CandList seat_candidates(
    double tcx, double tcy, int n, double step, double halo,
    double bound_eff, double keep_min, bool forbid_plus_x, int cap,
    const Box4& icb,
    const std::vector<Box4>& skeleton,
    const std::vector<double>& rots,
    const std::vector<Box4>& bodies,
    const std::vector<std::vector<Box4>>& rel_pads,
    const std::vector<Box4>& target_pins,
    const std::vector<Box4>& keep_pins);

DfsResult seat_dfs(const std::vector<std::vector<Box4>>& cand_boxes,
                   const std::vector<Box4>& skeleton,
                   double halo, int node_budget);

}  // namespace schgen
