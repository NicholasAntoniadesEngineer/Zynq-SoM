#include "schgen/pack_refine.hpp"

#include "schgen/occupancy.hpp"
#include "schgen/occupancy_precision.hpp"

#include <cmath>
#include <algorithm>
#include <limits>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>

namespace schgen {
namespace {

void rebuild_anchor(
    PackAnchorIn& anchor, const RefineBlock& block,
    const std::unordered_map<std::string, std::pair<double, double>>&
        centers) {
    anchor.block_w = block.w;
    anchor.block_h = block.h;
    anchor.affinity.clear();
    if (!block.pull_to.empty()) {
        auto found = centers.find(block.pull_to);
        if (found != centers.end()) {
            anchor.has_soft_pull = true;
            anchor.pull_x = found->second.first;
            anchor.pull_y = found->second.second;
        } else {
            anchor.has_soft_pull = false;
            anchor.pull_x = 0.0;
            anchor.pull_y = 0.0;
        }
    } else {
        anchor.has_soft_pull = false;
        anchor.pull_x = 0.0;
        anchor.pull_y = 0.0;
    }
    for (const auto& kv : block.aff_named) {
        auto found = centers.find(kv.first);
        if (found == centers.end()) {
            continue;
        }
        anchor.affinity.emplace_back(found->second.first, found->second.second,
                                     kv.second);
    }
}

}  // namespace

RefineResult refine_pack_passes(
    const Occupancy& occupancy, std::vector<RefineBlock> blocks,
    const std::unordered_map<std::string, std::pair<double, double>>&
        start_centers,
    int max_passes, double board_w, double board_h, QuantizationCounts* counts) {
    if (max_passes < 1) {
        throw std::runtime_error("refine_pack_passes: max_passes required");
    }
    Occupancy working = occupancy;
    working.set_board(board_w, board_h);
    auto centers = start_centers;
    const double wx0 = -board_w;
    const double wx1 = 2.0 * board_w;
    const double wy0 = -board_h;
    const double wy1 = 2.0 * board_h;
    int used = 0;
    for (int pass = 0; pass < max_passes; ++pass) {
        bool moved = false;
        for (RefineBlock& block : blocks) {
            working.remove(block.x, block.y, block.w, block.h, block.reach,
                           block.inset, block.mask, block.comps, counts);
            rebuild_anchor(block.anchor, block, centers);
            const auto anchor = pack_anchor(block.anchor);
            auto hit = working.place_near(anchor.first, anchor.second, block.w,
                                          block.h, block.reach, block.inset,
                                          block.mask, block.comps, wx0, wx1,
                                          wy0, wy1, counts);
            if (!hit.has_value()) {
                working.add(block.x, block.y, block.w, block.h, block.reach,
                            block.inset, block.mask, block.comps, counts);
                continue;
            }
            if (hit->x != block.x || hit->y != block.y) {
                moved = true;
            }
            block.x = hit->x;
            block.y = hit->y;
            working.add(block.x, block.y, block.w, block.h, block.reach,
                        block.inset, block.mask, block.comps, counts);
            centers[block.name] = {block.x + block.w / 2.0,
                                   block.y + block.h / 2.0};
        }
        used = pass + 1;
        if (!moved) {
            break;
        }
    }
    RefineResult out;
    out.passes = used;
    out.poses.reserve(blocks.size());
    for (const auto& block : blocks) {
        out.poses.emplace_back(block.x, block.y);
    }
    return out;
}

static std::vector<SeatShapeHit> seat_shapes(
    const Occupancy& occupancy, double anchor_x, double anchor_y,
    const std::vector<SeatShapeCand>& cands, double board_w, double board_h,
    double clear, QuantizationCounts* counts, bool keep_all) {
    Occupancy working = occupancy;
    working.set_board(board_w, board_h);
    std::vector<std::string> side_order;
    std::unordered_map<std::string, SeatShapeHit> best;
    std::vector<SeatShapeHit> all;
    for (const auto& cand : cands) {
        if (cand.w > board_w - 2.0 * clear || cand.h > board_h - 2.0 * clear) {
            continue;
        }
        auto pos = working.place_near(anchor_x, anchor_y, cand.w, cand.h,
                                      cand.reach, cand.inset, cand.mask,
                                      cand.comps, cand.win_x0, cand.win_x1,
                                      cand.win_y0, cand.win_y1, counts);
        if (!pos.has_value()) {
            continue;
        }
        const double dist = std::fabs(pos->x + cand.w / 2.0 - anchor_x)
            + std::fabs(pos->y + cand.h / 2.0 - anchor_y);
        const double dist_key = occupancy_shape_key4dp(dist, counts);
        auto found = keep_all ? best.end() : best.find(cand.side);
        if (!keep_all && found != best.end()) {
            if (dist_key > found->second.dist_key) {
                continue;
            }
            if (dist_key == found->second.dist_key
                && cand.index >= found->second.index) {
                continue;
            }
        } else if (!keep_all && found == best.end()) {
            side_order.push_back(cand.side);
        }
        SeatShapeHit hit;
        hit.side = cand.side;
        hit.index = cand.index;
        hit.x = pos->x;
        hit.y = pos->y;
        hit.w = cand.w;
        hit.h = cand.h;
        hit.reach = cand.reach;
        hit.inset = cand.inset;
        hit.comps = cand.comps;
        hit.dist_key = dist_key;
        if (keep_all) all.push_back(std::move(hit));
        else best[cand.side] = std::move(hit);
    }
    if (keep_all) return all;
    std::vector<SeatShapeHit> out;
    out.reserve(side_order.size());
    for (const auto& side : side_order) {
        out.push_back(best[side]);
    }
    return out;
}

std::vector<SeatShapeHit> seat_shape_sides(const Occupancy& occupancy,
    double anchor_x, double anchor_y, const std::vector<SeatShapeCand>& cands,
    double board_w, double board_h, double clear, QuantizationCounts* counts) {
    return seat_shapes(occupancy,anchor_x,anchor_y,cands,board_w,board_h,clear,counts,false);
}
std::vector<SeatShapeHit> seat_shape_candidates(const Occupancy& occupancy,
    double anchor_x, double anchor_y, const std::vector<SeatShapeCand>& cands,
    double board_w, double board_h, double clear, QuantizationCounts* counts) {
    return seat_shapes(occupancy,anchor_x,anchor_y,cands,board_w,board_h,clear,counts,true);
}

double packing_area_lower_bound(const std::vector<std::vector<PackingAreaOption>>& bodies,
                               int top_mask, int bottom_mask) {
    if (top_mask<=0 || bottom_mask<=0 || (top_mask&bottom_mask))
        throw std::invalid_argument("packing area requires disjoint face masks");
    double top=0, bottom=0, combined=0;
    for (const auto& body:bodies) {
        if (body.empty()) throw std::invalid_argument("packing body has no variants");
        double t=std::numeric_limits<double>::infinity(),b=t,total=t;
        for (const auto& option:body) {
            if (!std::isfinite(option.area) || option.area<0 || option.mask<=0 ||
                (option.mask&~(top_mask|bottom_mask)))
                throw std::invalid_argument("invalid packing area variant");
            const double ta=(option.mask&top_mask) ? option.area:0;
            const double ba=(option.mask&bottom_mask) ? option.area:0;
            t=std::min(t,ta); b=std::min(b,ba); total=std::min(total,ta+ba);
        }
        top+=t; bottom+=b; combined+=total;
    }
    // The minimum load of each individual face and half the minimum total
    // load are necessary bounds, never a claim that rectangles can be packed.
    const double result=std::max({top,bottom,combined/2});
    if (!std::isfinite(result)) throw std::overflow_error("packing area overflow");
    return result;
}

}  // namespace schgen
