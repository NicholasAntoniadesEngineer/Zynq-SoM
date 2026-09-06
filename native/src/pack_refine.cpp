#include "schgen/pack_refine.hpp"

#include "schgen/occupancy.hpp"

#include <cmath>
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
    int max_passes, double board_w, double board_h) {
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
                           block.inset, block.mask, block.comps);
            rebuild_anchor(block.anchor, block, centers);
            const auto anchor = pack_anchor(block.anchor);
            auto hit = working.place_near(anchor.first, anchor.second, block.w,
                                          block.h, block.reach, block.inset,
                                          block.mask, block.comps, wx0, wx1,
                                          wy0, wy1);
            if (!hit.has_value()) {
                working.add(block.x, block.y, block.w, block.h, block.reach,
                            block.inset, block.mask, block.comps);
                continue;
            }
            if (hit->x != block.x || hit->y != block.y) {
                moved = true;
            }
            block.x = hit->x;
            block.y = hit->y;
            working.add(block.x, block.y, block.w, block.h, block.reach,
                        block.inset, block.mask, block.comps);
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

std::vector<SeatShapeHit> seat_shape_sides(
    const Occupancy& occupancy, double anchor_x, double anchor_y,
    const std::vector<SeatShapeCand>& cands, double board_w, double board_h,
    double clear) {
    Occupancy working = occupancy;
    working.set_board(board_w, board_h);
    std::vector<std::string> side_order;
    std::unordered_map<std::string, SeatShapeHit> best;
    for (const auto& cand : cands) {
        if (cand.w > board_w - 2.0 * clear || cand.h > board_h - 2.0 * clear) {
            continue;
        }
        auto pos = working.place_near(anchor_x, anchor_y, cand.w, cand.h,
                                      cand.reach, cand.inset, cand.mask,
                                      cand.comps, cand.win_x0, cand.win_x1,
                                      cand.win_y0, cand.win_y1);
        if (!pos.has_value()) {
            continue;
        }
        const double dist = std::fabs(pos->x + cand.w / 2.0 - anchor_x)
            + std::fabs(pos->y + cand.h / 2.0 - anchor_y);
        const double dist_key = py_round(dist, 4);
        auto found = best.find(cand.side);
        if (found != best.end()) {
            if (dist_key > found->second.dist_key) {
                continue;
            }
            if (dist_key == found->second.dist_key
                && cand.index >= found->second.index) {
                continue;
            }
        } else {
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
        best[cand.side] = std::move(hit);
    }
    std::vector<SeatShapeHit> out;
    out.reserve(side_order.size());
    for (const auto& side : side_order) {
        out.push_back(best[side]);
    }
    return out;
}

}  // namespace schgen
