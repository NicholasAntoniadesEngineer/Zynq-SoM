#include "schgen/ladder_stub_rule.hpp"

#include <algorithm>
#include <sstream>

namespace schgen {

using ladder_stub_constants::stub_quantum;

bool ladder_stub_joins_pad(const EscapeLadderSeg& seg) {
    return seg.role == "stub_pair" || seg.role == "stub_column" || seg.role == "stub_pad";
}

std::optional<std::string> ladder_stub_violation(const EscapeLadderSeg& seg, double pad_width, double native_gap,
                                                 double normal_floor, const std::vector<LadderStubObstacle>& obstacles,
                                                 LadderStubEvidence& evidence) {
    std::ostringstream why;
    if (ladder_stub_joins_pad(seg) && seg.w > pad_width + stub_quantum.value) {
        why << seg.role << " is " << seg.w << " mm wide, wider than the " << pad_width << " mm pad it joins";
        return why.str();
    }
    for (const auto& obstacle : obstacles) {
        const double centre = seg_box_dist(seg.ax, seg.ay, seg.bx, seg.by, {obstacle.x0, obstacle.y0, obstacle.x1, obstacle.y1});
        const double gap = centre - seg.w / 2;
        if (obstacle.same_footprint) {
            evidence.nearest_same = std::min(evidence.nearest_same, gap);
            if (gap + stub_quantum.value < native_gap) {
                why << seg.role << " comes " << gap << " mm from " << obstacle.label << ", closer than the land pattern's own "
                    << native_gap << " mm pad gap";
                return why.str();
            }
            continue;
        }
        evidence.nearest_other = std::min(evidence.nearest_other, gap);
        const double need = std::max(normal_floor, obstacle.rule);
        if (gap < need) {
            why << seg.role << " comes " << gap << " mm from " << obstacle.label << ", the clearance rule needs " << need << " mm";
            return why.str();
        }
    }
    return std::nullopt;
}

std::string ladder_stub_report(const LadderStubEvidence& evidence) {
    std::ostringstream text;
    text << "LADDER STUB RULE " << evidence.connector << ": stub width = pad width " << evidence.pad_width
         << " mm; same-footprint pads judged against the land pattern's own gap " << evidence.native_gap
         << " mm (fabricator minimum " << evidence.fab_minimum << " mm); nearest same-footprint pad " << evidence.nearest_same
         << " mm, nearest other copper " << evidence.nearest_other << " mm; " << evidence.kept << " stubs kept, "
         << evidence.dropped.size() << " dropped";
    for (const auto& drop : evidence.dropped) text << "\n    dropped " << drop;
    return text.str();
}

}
