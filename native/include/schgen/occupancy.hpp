#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <unordered_map>
#include <utility>
#include <vector>

namespace schgen {

struct Halo {
    double w = 0.0;
    double e = 0.0;
    double n = 0.0;
    double s = 0.0;
};

struct Comp {
    double dx = 0.0;
    double dy = 0.0;
    double w = 0.0;
    double h = 0.0;
    int mask = 0;
};

struct Pose {
    double x = 0.0;
    double y = 0.0;
    double w = 0.0;
    double h = 0.0;
};

struct CellKey {
    int x = 0;
    int y = 0;
    bool operator==(const CellKey& o) const { return x == o.x && y == o.y; }
};

struct CellKeyHash {
    std::size_t operator()(const CellKey& k) const {
        return (static_cast<std::size_t>(static_cast<uint32_t>(k.x)) << 32)
            ^ static_cast<uint32_t>(k.y);
    }
};

struct Rect {
    double x = 0.0;
    double y = 0.0;
    double w = 0.0;
    double h = 0.0;
    Halo reach;
    Halo inset;
    int mask = 0;
    int pmask = 0;
    bool main = true;
};

class Occupancy {
public:
    Occupancy(double board_w, double board_h, double clear, double bucket,
              double reach_bound, double step, double frontier_half);

    void set_board(double board_w, double board_h);
    void add(double x, double y, double w, double h, const Halo& reach,
             const Halo& inset, int mask, const std::vector<Comp>& comps);
    void remove(double x, double y, double w, double h, const Halo& reach,
                const Halo& inset, int mask, const std::vector<Comp>& comps);
    bool fits_exhaustive(double x, double y, double w, double h,
                         const Halo& reach, const Halo& inset, int mask,
                         const std::vector<Comp>& comps) const;
    bool fits_hashed(double x, double y, double w, double h,
                     const Halo& reach, const Halo& inset, int mask,
                     const std::vector<Comp>& comps) const;
    std::optional<Pose> place_near(double ax, double ay, double w, double h,
                                   const Halo& reach, const Halo& inset,
                                   int mask, const std::vector<Comp>& comps,
                                   double win_x0, double win_x1,
                                   double win_y0, double win_y1) const;
    std::size_t rect_count() const { return rects_.size(); }

private:
    void add_one(double x, double y, double w, double h, const Halo& reach,
                 const Halo& inset, int mask, int pmask, bool main);
    void remove_one(double x, double y, double w, double h, const Halo& reach,
                    const Halo& inset, int mask, int pmask, bool main);
    bool body_clear(double x, double y, double w, double h, const Halo& reach,
                    const Halo& inset, int qmask, int qpmask, bool qmain,
                    bool hashed) const;
    bool query_hashed_cells(double x, double y, double w, double h,
                            const Halo& qh, const Halo& reach,
                            const Halo& inset, int qmask, int qpmask,
                            bool qmain) const;

    double board_w_;
    double board_h_;
    double clear_;
    double bucket_;
    double reach_bound_;
    double step_;
    double frontier_half_;
    std::vector<Rect> rects_;
    std::unordered_map<CellKey, std::vector<Rect>, CellKeyHash> cells_;
};

double fanout_sep(const Halo& a_reach, const Halo& a_inset,
                  const Halo& b_reach, const Halo& b_inset, char axis);
Halo halo4(const Halo& reach, const Halo& inset);
bool occ_pair_active(int a_mask, int a_pmask, bool a_main,
                     int b_mask, int b_pmask, bool b_main);
double py_round(double value, int digits);
bool boxes_separated(double ax, double ay, double aw, double ah,
                     double bx, double by, double bw, double bh,
                     double gx, double gy);

}  // namespace schgen
