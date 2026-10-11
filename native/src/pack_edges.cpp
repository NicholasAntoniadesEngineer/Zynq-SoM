#include "schgen/pack_edges.hpp"
#include "schgen/pack_precision.hpp"
#include "edge_feasible_start_internal.hpp"

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

#include "schgen/occupancy.hpp"
#include "schgen/pack.hpp"
#include "schgen/legalize.hpp"

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
                      char edge, const PackEdgesSpec& spec, QuantizationCounts* counts) {
    if (a.overmold && b.overmold) {
        return spec.cable_neighbor_gap;
    }
    // Fanout is along this placement's edge, never a previous attempt's edge.
    // A fresh block may have no current_edge; a spilled block may have another.
    const char axis = is_ns(edge) ? 'E' : 'S';
    const double floor = (a.overmold || b.overmold) ? spec.overmold_side_gap
                                                    : spec.clear;
    return pair_gap(a.reach, a.inset, b.reach, b.inset, axis, floor, counts);
}

double rounded_run_coordinate(double target,double lower,QuantizationCounts* counts) {
    double value=pack_edge_pose_precision4dp(target,counts);
    if(value>=lower)return value;
    // Project onto the existing output grid, then recheck the actual floating
    // expression. Decimal ceiling alone can still land below the bound.
    const double tick=pack_edge_lower_tick_ceil(lower,counts);
    value=pack_edge_pose_precision4dp(tick/10000.0,counts);
    if(value<lower)value=pack_edge_pose_precision4dp((tick+1.0)/10000.0,counts);
    if(!(value>=lower))throw std::runtime_error("pack_edges: no representable safe run coordinate");
    return value;
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
                                      double template_clear, double hx, QuantizationCounts* counts) {
    return {pack_hf_cap_pose_precision4dp(inductor_left - template_clear - hx, counts), beside_oy};
}

PackEdgesResult pack_edges(const std::vector<PackEdgeBlock>& blocks,
                           const std::vector<PackEdgeJack>& jacks,
                           const PackEdgesSpec& spec, QuantizationCounts* counts,
                           const std::vector<Box4>* initial_keepouts) {
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
    std::vector<EdgeFanoutBlock> seated;
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
                blocks[static_cast<std::size_t>(order[i + 1])], edge, spec, counts));
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
        if(initial_keepouts) {
            ++out.feasibility_runs;
            if(hi-total<lo){++out.feasibility_rejections;return out;}
            double feasible_low=lo,feasible_high=hi-total;
            std::vector<std::pair<double,double>> forbidden;
            for(std::size_t i=0;i<order.size();++i) {
                const auto& block=blocks[static_cast<std::size_t>(order[i])];
                const double offset=offs[i]-span_of(block,edge)/2.0;
                feasible_low=std::max(feasible_low,spec.edge_margin+(is_ns(edge)?block.reach.w:block.reach.n)-offset);
                feasible_high=std::min(feasible_high,span-spec.edge_margin-(is_ns(edge)?block.reach.e:block.reach.s)-span_of(block,edge)-offset);
                const double transverse=edge=='N'||edge=='W'?spec.edge_inset:
                    pack_edge_pose_precision4dp((edge=='S'?spec.board_h:spec.board_w)-depth_of(block,edge)-spec.edge_inset,counts);
                const EdgeFanoutBlock moving{is_ns(edge)?0:transverse,is_ns(edge)?transverse:0,
                    block.w,block.h,block.reach,block.inset,edge};
                const auto add=[&](const EdgeFanoutBlock& obstacle,double clearance,bool body_only){
                    auto box=moving;
                    if(body_only){box.reach={};box.inset={};}
                    if(const auto interval=floorplan_detail::edge_collision_interval(box,obstacle,is_ns(edge),clearance)) {
                        forbidden.emplace_back(interval->first-offset,interval->second-offset);
                        ++out.feasibility_intervals;
                    }
                };
                for(const auto& obstacle:seated)add(obstacle,spec.clear,false);
                for(const auto& ko:*initial_keepouts)add({ko.x0,ko.y0,ko.x1-ko.x0,ko.y1-ko.y0,{},{},'\0'},0,true);
            }
            if(feasible_low>feasible_high){++out.feasibility_rejections;return out;}
            const auto feasible=floorplan_detail::nearest_feasible_edge_start(start,feasible_low,feasible_high,forbidden);
            if(!feasible){++out.feasibility_rejections;return out;}
            start=*feasible;
        }
        double pos = start;
        double lower = lo;
        const auto run_begin=out.poses.size();
        bool run_overflow=false;
        for (std::size_t i = 0; i < order.size(); ++i) {
            const PackEdgeBlock& block =
                blocks[static_cast<std::size_t>(order[i])];
            const double sp = span_of(block, edge);
            const double dp = depth_of(block, edge);
            PackEdgePose pose;
            pose.name = block.name;
            pose.edge = std::string(1, edge);
            const double along=rounded_run_coordinate(pos,lower,counts);
            if(along+sp>hi)run_overflow=true;
            if (edge == 'N') {
                pose.x = along;
                pose.y = spec.edge_inset;
            } else if (edge == 'S') {
                pose.x = along;
                pose.y = pack_edge_pose_precision4dp(spec.board_h - dp - spec.edge_inset, counts);
            } else if (edge == 'W') {
                pose.x = spec.edge_inset;
                pose.y = along;
            } else {
                pose.x = pack_edge_pose_precision4dp(spec.board_w - dp - spec.edge_inset, counts);
                pose.y = along;
            }
            out.poses.push_back(pose);
            lower = along + sp + (i < gaps.size() ? gaps[i] : 0.0);
            pos += sp + (i < gaps.size() ? gaps[i] : 0.0);
        }
        // Projection cannot buy clearance by crossing the far run boundary.
        // Missing poses make the owning floorplan reject this outline.
        if(run_overflow)out.poses.resize(run_begin);
        if(initial_keepouts) {
            auto candidate=seated;
            std::vector<Box4> bodies;
            bool actual_valid=!run_overflow;
            for(std::size_t i=run_begin;i<out.poses.size();++i) {
                const auto& p=out.poses[i];
                const auto& block=blocks[static_cast<std::size_t>(order[i-run_begin])];
                candidate.push_back({p.x,p.y,block.w,block.h,block.reach,block.inset,edge});
                bodies.push_back({p.x,p.y,p.x+block.w,p.y+block.h});
                const double along=is_ns(edge)?p.x:p.y;
                if(along<spec.edge_margin+(is_ns(edge)?block.reach.w:block.reach.n)||
                   along+span_of(block,edge)>span-spec.edge_margin-(is_ns(edge)?block.reach.e:block.reach.s))actual_valid=false;
            }
            for(std::size_t i=seated.size();i<candidate.size();++i)
                for(std::size_t j=i+1;j<candidate.size();++j) {
                    const auto& a=candidate[i];const auto& b=candidate[j];
                    const auto gx=std::max(spec.clear,fanout_sep(a.reach,a.inset,b.reach,b.inset,a.x<=b.x?'E':'W'));
                    const auto gy=std::max(spec.clear,fanout_sep(a.reach,a.inset,b.reach,b.inset,a.y<=b.y?'S':'N'));
                    if(!boxes_separated(a.x,a.y,a.w,a.h,b.x,b.y,b.w,b.h,gx,gy))actual_valid=false;
                }
            // The analytical answer is only a proposal. Actual emitted poses
            // must satisfy the independent physical predicate, with no epsilon
            // added to cross-edge clearance or keepout contact.
            if(!actual_valid||!cross_edge_fanout_hold(candidate,spec.clear)||rects_overlap_any(bodies,*initial_keepouts,0)) {
                out.poses.resize(run_begin);++out.feasibility_rejections;return out;
            }
            seated=std::move(candidate);
        }
    }
    return out;
}

}  // namespace schgen
