#pragma once
#include <algorithm>
#include <cmath>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

namespace schgen {
// Neutral value transport: no placement/catalog/geometry dependencies, policy
// thresholds, ownership inference, or additional movement permissions.
enum class OwnedShapeQualityState { NotApplicable, Measured, Rejected };
enum class OwnedShapeRole { Bypass, OutputBulk };
struct OwnedShapeSubject {
    // Map key is the board capacitor reference. All identity fields use the
    // same trusted board namespace, including supply/return net names.
    std::string owner, owner_pin, cap_pin, return_pin, rail, return_net;
    std::string owner_side, cap_side;
    OwnedShapeRole role = OwnedShapeRole::Bypass;
    bool operator==(const OwnedShapeSubject& b) const {
        return std::tie(owner, owner_pin, cap_pin, return_pin, rail, return_net,
                        owner_side, cap_side, role) ==
               std::tie(b.owner, b.owner_pin, b.cap_pin, b.return_pin, b.rail, b.return_net,
                        b.owner_side, b.cap_side, b.role);
    }
};
struct OwnedShapeMeasurement {
    std::string owner, owner_pin, member, member_pin, owner_side, member_side;
    double planar_pad_box_gap_mm = 0;
};
struct OwnedShapeQuality {
    OwnedShapeQualityState state = OwnedShapeQualityState::NotApplicable;
    std::map<std::string, double> bypass_pad_gaps, bulk_pad_gaps;
    std::vector<OwnedShapeMeasurement> measurements; // reporting, local references
    std::optional<int> fanout_starved;
    std::vector<std::string> diagnostics;
    std::map<std::string, OwnedShapeSubject> subjects; // comparison, board references
};
using OwnedShapeQualityTable = std::map<std::pair<std::string, int>, OwnedShapeQuality>;

inline bool owned_shape_quality_comparable(const OwnedShapeQuality& a,
                                           const OwnedShapeQuality& b) {
    if (a.state != OwnedShapeQualityState::Measured || b.state != OwnedShapeQualityState::Measured ||
        a.subjects.empty() || a.subjects != b.subjects || a.bypass_pad_gaps.empty() ||
        !a.fanout_starved || !b.fanout_starved || *a.fanout_starved < 0 ||
        *b.fanout_starved < 0 || a.fanout_starved != b.fanout_starved) return false;
    const auto complete = [](const OwnedShapeQuality& q) {
        if (q.subjects.size() != q.bypass_pad_gaps.size() + q.bulk_pad_gaps.size()) return false;
        for (const auto& [cap, s] : q.subjects) {
            if (cap.empty() || s.owner.empty() || s.owner == cap || s.owner_pin.empty() ||
                s.cap_pin.empty() || s.return_pin.empty() || s.cap_pin == s.return_pin ||
                s.rail.empty() || s.return_net.empty() || s.rail == s.return_net ||
                (s.owner_side != "top" && s.owner_side != "bottom") ||
                (s.cap_side != "top" && s.cap_side != "bottom")) return false;
            if (s.role != OwnedShapeRole::Bypass && s.role != OwnedShapeRole::OutputBulk) return false;
            const auto& values = s.role == OwnedShapeRole::Bypass ? q.bypass_pad_gaps : q.bulk_pad_gaps;
            const auto& other = s.role == OwnedShapeRole::Bypass ? q.bulk_pad_gaps : q.bypass_pad_gaps;
            const auto gap = values.find(cap);
            if (gap == values.end() || other.count(cap) || !std::isfinite(gap->second) || gap->second < 0) return false;
        }
        return true;
    };
    return complete(a) && complete(b);
}

// Strict Pareto dominance only, NOT a strict-weak ordering for std::sort.
// Reporting rows are not ranking authority; typed subjects and per-cap gaps
// are the canonical comparison data. Bulk stays equal and is never optimized.
inline bool owned_shape_pareto_dominates(const OwnedShapeQuality& challenger,
                                       const OwnedShapeQuality& incumbent) {
    if (!owned_shape_quality_comparable(challenger, incumbent) ||
        challenger.bulk_pad_gaps != incumbent.bulk_pad_gaps) return false;
    bool improved = false;
    for (const auto& [cap, before] : incumbent.bypass_pad_gaps) {
        const double after = challenger.bypass_pad_gaps.at(cap);
        if (after > before) return false;
        improved |= after < before;
    }
    return improved;
}

struct OwnedShapeTieRank {
    int index = 0;
    bool feasible = false;
    double w = 0, h = 0, estimator = 0, distance_key = 0;
    std::string side;
};
inline bool owned_shape_valid_tie_rank(const OwnedShapeTieRank& r) {
        return r.feasible && r.index >= 0 && std::isfinite(r.w) && r.w > 0 &&
            std::isfinite(r.h) && r.h > 0 && std::isfinite(r.estimator) &&
            std::isfinite(r.distance_key) && r.distance_key >= 0 &&
            (r.side == "top" || r.side == "bottom");
}
inline bool owned_shape_same_primary_rank(const OwnedShapeTieRank& a, const OwnedShapeTieRank& b) {
    return owned_shape_valid_tie_rank(a) && owned_shape_valid_tie_rank(b) &&
        a.w == b.w && a.h == b.h && a.estimator == b.estimator &&
        a.distance_key == b.distance_key && a.side == b.side;
}
// Guarded dominance predicate. No stable-index fallback here. Exact equality
// does NOT widen the estimator's established tolerance into a quality band.
inline bool owned_shape_tie_dominates(bool compact, const OwnedShapeQualityTable& quality,
    const std::string& sheet, const OwnedShapeTieRank& challenger, const OwnedShapeTieRank& incumbent) {
    if (!compact || sheet.empty() || challenger.index == incumbent.index ||
        !owned_shape_same_primary_rank(challenger, incumbent)) return false;
    const auto a = quality.find({sheet, challenger.index}), b = quality.find({sheet, incumbent.index});
    return a != quality.end() && b != quality.end() && owned_shape_pareto_dominates(a->second, b->second);
}

// Caller supplies ONE complete equal-primary-rank bucket, after existing
// feasibility/area/estimator ranking. Evaluate dominance against the ENTIRE
// bucket, not a running incumbent. Only afterwards order survivors by the
// existing stable shape index. This is invariant under bucket permutations.
// Missing/incompatible/invalid quality stays incomparable, never zero-valued.
// Malformed primary buckets reject instead of silently crossing rank classes.
inline std::vector<int> owned_shape_nondominated_indices(bool compact,
    const OwnedShapeQualityTable& quality, const std::string& sheet,
    const std::vector<OwnedShapeTieRank>& bucket) {
    if (bucket.empty()) return {};
    if (sheet.empty()) throw std::invalid_argument("owned quality bucket requires a sheet");
    std::set<int> indices;
    for (const auto& rank : bucket)
        if (!owned_shape_same_primary_rank(rank, bucket.front()) || !indices.insert(rank.index).second)
            throw std::invalid_argument("owned quality bucket requires unique feasible indices and equal finite primary ranks");
    std::vector<int> survivors;
    for (const auto& candidate : bucket) {
        const bool dominated = std::any_of(bucket.begin(), bucket.end(), [&](const auto& other) {
            return owned_shape_tie_dominates(compact, quality, sheet, other, candidate);
        });
        if (!dominated) survivors.push_back(candidate.index);
    }
    std::sort(survivors.begin(), survivors.end()); // integer indices ONLY
    return survivors;
}
inline std::optional<int> owned_shape_select_tied_bucket(bool compact,
    const OwnedShapeQualityTable& quality, const std::string& sheet,
    const std::vector<OwnedShapeTieRank>& bucket) {
    const auto survivors = owned_shape_nondominated_indices(compact, quality, sheet, bucket);
    return survivors.empty() ? std::nullopt : std::optional<int>{survivors.front()};
}
}
