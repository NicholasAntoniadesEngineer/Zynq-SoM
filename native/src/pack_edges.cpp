#include "schgen/pack_edges.hpp"

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

#include "schgen/occupancy.hpp"
#include "schgen/pack.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace schgen {
namespace {

bool is_ns(char edge) {
    return edge == 'N' || edge == 'S';
}

char require_edge(const std::string& edge, const char* where) {
    if (edge.size() != 1 || std::string("NESW").find(edge[0]) == std::string::npos) {
        throw std::runtime_error(std::string(where) + ": edge must be N/E/S/W");
    }
    return edge[0];
}

char spill_next(char edge) {
    switch (edge) {
        case 'W':
            return 'S';
        case 'S':
            return 'N';
        case 'N':
            return 'E';
        case 'E':
            return 'W';
        default:
            throw std::runtime_error("pack_edges: invalid spill edge");
    }
}

double span_of(const PackEdgeBlock& block, char edge) {
    return is_ns(edge) ? block.w : block.h;
}

double depth_of(const PackEdgeBlock& block, char edge) {
    return is_ns(edge) ? block.h : block.w;
}

double aff_sum(const std::vector<std::pair<std::string, double>>& j_aff) {
    double total = 0.0;
    for (const auto& kv : j_aff) {
        total += kv.second;
    }
    return total;
}

double block_pair_gap(const PackEdgeBlock& a, const PackEdgeBlock& b,
                      const PackEdgesSpec& spec) {
    if (a.overmold && b.overmold) {
        return spec.cable_neighbor_gap;
    }
    const std::string& use = !a.current_edge.empty() ? a.current_edge
                                                     : b.current_edge;
    const char axis = (use == "N" || use == "S") ? 'E' : 'S';
    const double floor = (a.overmold || b.overmold) ? spec.overmold_side_gap
                                                    : spec.clear;
    return pair_gap(a.reach, a.inset, b.reach, b.inset, axis, floor);
}

}  // namespace

double edge_target(char edge, const PackEdgesSpec& spec,
                   const std::vector<std::pair<std::string, double>>& j_aff,
                   const std::vector<PackEdgeJack>& jacks) {
    const int axis = is_ns(edge) ? 0 : 1;
    double weighted = 0.0;
    double total = 0.0;
    for (const auto& kv : j_aff) {
        for (const auto& jack : jacks) {
            if (jack.ref != kv.first) {
                continue;
            }
            const double pos = axis == 0 ? jack.x : jack.y;
            weighted += kv.second * pos;
            total += kv.second;
            break;
        }
    }
    if (total == 0.0) {
        return axis == 0 ? (spec.som_x + spec.som_w / 2.0)
                         : (spec.som_y + spec.som_h / 2.0);
    }
    return weighted / total;
}

bool pick_sided_challenger(double est_inc, double est_chal, double eps) {
    return est_chal < est_inc - eps;
}

std::vector<int> reseat_rank(
    double anchor_x, double anchor_y,
    const std::vector<std::tuple<double, double, double, double, std::string>>&
        placed) {
    std::vector<std::tuple<double, int, std::string, int>> keys;
    keys.reserve(placed.size());
    for (std::size_t i = 0; i < placed.size(); ++i) {
        const auto& row = placed[i];
        const double cx = std::get<0>(row) + std::get<2>(row) / 2.0;
        const double cy = std::get<1>(row) + std::get<3>(row) / 2.0;
        const double dist = std::fabs(cx - anchor_x) + std::fabs(cy - anchor_y);
        keys.emplace_back(dist, static_cast<int>(i), std::get<4>(row),
                          static_cast<int>(i));
    }
    std::sort(keys.begin(), keys.end());
    std::vector<int> out;
    out.reserve(keys.size());
    for (const auto& key : keys) {
        out.push_back(std::get<3>(key));
    }
    return out;
}

std::pair<double, double> hf_cap_pose(double beside_oy, double inductor_left,
                                      double template_clear, double hx) {
    return {py_round(inductor_left - template_clear - hx, 4), beside_oy};
}

PackEdgesResult pack_edges(const std::vector<PackEdgeBlock>& blocks,
                           const std::vector<PackEdgeJack>& jacks,
                           const PackEdgesSpec& spec) {
    std::vector<int> pending[4];
    auto slot = [](char edge) -> int {
        switch (edge) {
            case 'N':
                return 0;
            case 'E':
                return 1;
            case 'S':
                return 2;
            case 'W':
                return 3;
            default:
                throw std::runtime_error("pack_edges: assigned edge required");
        }
    };
    const char cycle[4] = {'W', 'S', 'N', 'E'};
    for (std::size_t i = 0; i < blocks.size(); ++i) {
        const char assigned = require_edge(blocks[i].assigned_edge,
                                           "pack_edges assigned");
        pending[slot(assigned)].push_back(static_cast<int>(i));
    }
    std::vector<int> placed[4];
    std::vector<std::string> spilled;
    for (int round = 0; round < 4; ++round) {
        (void)round;
        for (char edge : cycle) {
            const int si = slot(edge);
            const double cap =
                (edge == 'W' || edge == 'E' ? spec.board_h : spec.board_w)
                - 2.0 * spec.edge_margin;
            double used = 0.0;
            for (int idx : placed[si]) {
                const double trail = blocks[static_cast<std::size_t>(idx)].overmold
                    ? spec.cable_neighbor_gap
                    : spec.clear;
                used += span_of(blocks[static_cast<std::size_t>(idx)], edge)
                    + trail;
            }
            std::vector<int> queue = pending[si];
            pending[si].clear();
            std::sort(queue.begin(), queue.end(),
                      [&](int ia, int ib) {
                          const double sa =
                              span_of(blocks[static_cast<std::size_t>(ia)],
                                      edge);
                          const double sb =
                              span_of(blocks[static_cast<std::size_t>(ib)],
                                      edge);
                          if (sa != sb) {
                              return sa > sb;
                          }
                          return blocks[static_cast<std::size_t>(ia)].name
                              < blocks[static_cast<std::size_t>(ib)].name;
                      });
            for (int idx : queue) {
                const PackEdgeBlock& block =
                    blocks[static_cast<std::size_t>(idx)];
                if (used + span_of(block, edge) <= cap) {
                    placed[si].push_back(idx);
                    const double trail = block.overmold ? spec.cable_neighbor_gap
                                                        : spec.clear;
                    used += span_of(block, edge) + trail;
                } else {
                    const char nxt = spill_next(edge);
                    pending[slot(nxt)].push_back(idx);
                    spilled.push_back(block.name + ": " + std::string(1, edge)
                                      + " edge full -> " + std::string(1, nxt));
                }
            }
        }
    }

    PackEdgesResult out;
    out.spilled = std::move(spilled);
    const char faces[4] = {'N', 'E', 'S', 'W'};
    for (char edge : faces) {
        const int si = slot(edge);
        std::vector<int> order = placed[si];
        if (order.empty()) {
            continue;
        }
        std::sort(order.begin(), order.end(), [&](int ia, int ib) {
            const PackEdgeBlock& a = blocks[static_cast<std::size_t>(ia)];
            const PackEdgeBlock& b = blocks[static_cast<std::size_t>(ib)];
            const bool ah = a.order_hint.has_value();
            const bool bh = b.order_hint.has_value();
            if (ah != bh) {
                return ah && !bh;
            }
            if (ah && bh && *a.order_hint != *b.order_hint) {
                return *a.order_hint < *b.order_hint;
            }
            if (!ah && !bh) {
                const double ta = edge_target(edge, spec, a.j_aff, jacks);
                const double tb = edge_target(edge, spec, b.j_aff, jacks);
                if (ta != tb) {
                    return ta < tb;
                }
            }
            return a.name < b.name;
        });
        const double span = (edge == 'W' || edge == 'E') ? spec.board_h
                                                         : spec.board_w;
        const PackEdgeBlock& first =
            blocks[static_cast<std::size_t>(order.front())];
        const PackEdgeBlock& last =
            blocks[static_cast<std::size_t>(order.back())];
        const double lo_r = is_ns(edge) ? first.reach.w : first.reach.n;
        const double hi_r = is_ns(edge) ? last.reach.e : last.reach.s;
        const double lo = spec.edge_margin + lo_r;
        const double hi = span - spec.edge_margin - hi_r;
        std::vector<double> gaps;
        gaps.reserve(order.size());
        for (std::size_t i = 0; i + 1 < order.size(); ++i) {
            gaps.push_back(block_pair_gap(
                blocks[static_cast<std::size_t>(order[i])],
                blocks[static_cast<std::size_t>(order[i + 1])], spec));
        }
        double total = 0.0;
        for (int idx : order) {
            total += span_of(blocks[static_cast<std::size_t>(idx)], edge);
        }
        for (double g : gaps) {
            total += g;
        }
        std::vector<double> offs;
        offs.reserve(order.size());
        double acc = 0.0;
        for (std::size_t i = 0; i < order.size(); ++i) {
            const double sp =
                span_of(blocks[static_cast<std::size_t>(order[i])], edge);
            offs.push_back(acc + sp / 2.0);
            acc += sp + (i < gaps.size() ? gaps[i] : 0.0);
        }
        std::vector<double> wts;
        wts.reserve(order.size());
        double wsum = 0.0;
        for (int idx : order) {
            const double wt =
                std::max(aff_sum(blocks[static_cast<std::size_t>(idx)].j_aff),
                         0.0)
                + spec.affinity_floor;
            wts.push_back(wt);
            wsum += wt;
        }
        double start = 0.0;
        for (std::size_t i = 0; i < order.size(); ++i) {
            const PackEdgeBlock& block =
                blocks[static_cast<std::size_t>(order[i])];
            const double tgt = edge_target(edge, spec, block.j_aff, jacks);
            start += wts[i] * (tgt - offs[i]);
        }
        start /= wsum;
        start = std::max(lo, std::min(start, hi - total));
        double pos = start;
        for (std::size_t i = 0; i < order.size(); ++i) {
            const PackEdgeBlock& block =
                blocks[static_cast<std::size_t>(order[i])];
            const double sp = span_of(block, edge);
            const double dp = depth_of(block, edge);
            PackEdgePose pose;
            pose.name = block.name;
            pose.edge = std::string(1, edge);
            if (edge == 'N') {
                pose.x = py_round(pos, 4);
                pose.y = spec.edge_inset;
            } else if (edge == 'S') {
                pose.x = py_round(pos, 4);
                pose.y = py_round(spec.board_h - dp - spec.edge_inset, 4);
            } else if (edge == 'W') {
                pose.x = spec.edge_inset;
                pose.y = py_round(pos, 4);
            } else {
                pose.x = py_round(spec.board_w - dp - spec.edge_inset, 4);
                pose.y = py_round(pos, 4);
            }
            out.poses.push_back(pose);
            pos += sp + (i < gaps.size() ? gaps[i] : 0.0);
        }
    }
    return out;
}

}  // namespace schgen
