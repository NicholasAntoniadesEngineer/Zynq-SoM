#include "pcb_placement_internal.hpp"
#include "schgen/board_decision_policy.hpp"
#include "schgen/legalize.hpp"

namespace schgen::pcb_placement {
void Placer::breathe(const std::string &phase) {
    constexpr double eps = 1e-4, step = .25;
    double pc = ctx.clearance;
    std::vector<std::string> movable, fixed_parts;
    std::set<std::string> contracted;
    for (const auto &[sheet, p] : origins) {
        (void)p;
        if (ctx.wired.count(sheet) && ctx.in.contracts.count(sheet))
            contracted.insert(sheet);
    }
    for (const auto &[r, p] : pos) {
        (void)p;
        if (!geometry.bbox_of.count(r) || !geometry.resolvable.count(r)) {
            fixed_parts.push_back(r);
            continue;
        }
        const auto &b = ctx.by_ref.at(r);
        bool immovable = b.sheet.rfind("som_j", 0) == 0 ||
                         std::find(geometry.mh_refs.begin(), geometry.mh_refs.end(), r) !=
                             geometry.mh_refs.end() ||
                         geometry.conn_edge.count(r) || b.sheet == "som_decoupling" ||
                         b.footprint.find("Fiducial") != std::string::npos ||
                         contracted.count(b.sheet) || contract_members.count(r) ||
                         ctx.l4_exempt.count(r);
        (immovable ? fixed_parts : movable).push_back(r);
    }
    if (movable.empty())
        return;
    BreatheGrid top(width, height, .25, 25, 25), bottom(width, height, .25, 25, 25);
    auto grid = [&](const std::string &r) -> BreatheGrid & {
        return side(r) == "bottom" ? bottom : top;
    };
    auto page_keepout = offset_rect(keepout, 25, 25);
    for (auto *g : {&top, &bottom}) {
        g->stamp({25, 25, 25 + width, 25 + .6}, 1);
        g->stamp({25, 25 + height - .6, 25 + width, 25 + height}, 1);
        g->stamp({25, 25, 25 + .6, 25 + height}, 1);
        g->stamp({25 + width - .6, 25, 25 + width, 25 + height}, 1);
        g->stamp(page_keepout, 1);
        g->stamp(grow_rect(page_keepout, 2), 1);
        for (const auto &[r, j] : som_refs) {
            (void)j;
            if (geometry.bbox_of.count(r) && pos.count(r))
                g->stamp(grow_rect(box(r, pos.at(r)), 6), 1);
        }
    }
    for (const auto &r : fixed_parts)
        if (geometry.bbox_of.count(r) && geometry.resolvable.count(r))
            grid(r).stamp(grow_rect(box(r, pos.at(r)), pc), 1);
    for (const auto &[r, p] : pos)
        if (side(r) == "top" && geometry.resolvable.count(r) && geometry.bbox_of.count(r) &&
            has_thru_pads_from_text(mod(r)->bytes))
            bottom.stamp(grow_rect(box(r, p), pc), 1);
    std::map<std::string, std::vector<std::string>> by_sheet;
    for (const auto &r : movable) {
        grid(r).stamp(grow_rect(box(r, pos.at(r)), pc / 2), 1);
        by_sheet[ctx.by_ref.at(r).sheet].push_back(r);
    }
    auto cp = [&](const std::string &r) {
        return is_cluster_passive(r, pins(r), {"RS", "RJ", "RN", "LED"}, {"R", "C", "L"});
    };
    struct Group {
        std::string anchor, sheet;
        std::set<std::string> members;
        double need = 0, target = 0, deficit = 0;
    };
    std::vector<Group> groups;
    for (const auto &[sheet, refs] : by_sheet) {
        std::vector<std::string> subjects;
        for (const auto &r : refs)
            if (pins(r) >= 3)
                subjects.push_back(r);
        if (subjects.empty())
            continue;
        std::map<std::string, std::set<std::string>> assigned;
        for (const auto &r : refs)
            if (pins(r) < 3) {
                auto best = *std::min_element(
                    subjects.begin(), subjects.end(), [&](const auto &a, const auto &b) {
                        auto p = pos.at(r), pa = pos.at(a), pb = pos.at(b);
                        return std::make_pair(std::hypot(pa.first - p.first, pa.second - p.second),
                                              a) <
                               std::make_pair(std::hypot(pb.first - p.first, pb.second - p.second),
                                              b);
                    });
                assigned[best].insert(r);
            }
        for (const auto &r : subjects) {
            assigned[r].insert(r);
            groups.push_back({r, sheet, assigned[r], need(pins(r)), need(pins(r)) + 1, 0});
        }
    }
    Offsets seed;
    for (const auto &r : movable)
        seed[r] = pos.at(r);
    std::map<std::string, FloorplanPoint> centroid;
    std::map<std::string, double> diag, area, disp;
    for (const auto &[sheet, refs] : by_sheet) {
        std::vector<FloorplanPoint> points;
        std::vector<Box4> boxes;
        double total = 0;
        for (const auto &r : refs) {
            points.push_back(pos.at(r));
            boxes.push_back(box(r, pos.at(r)));
            auto b = box(r, {0, 0});
            total += (b.x1 - b.x0) * (b.y1 - b.y0);
        }
        centroid[sheet] = points_centroid(points);
        auto b = *boxes_union(boxes);
        diag[sheet] = .5 * std::hypot(b.x1 - b.x0, b.y1 - b.y0);
        area[sheet] = total ? total : 1;
        disp[sheet] = (b.x1 - b.x0) * (b.y1 - b.y0) / area[sheet];
    }
    auto leash = [&](const Group &g, FloorplanPoint delta) {
        const auto &refs = by_sheet.at(g.sheet);
        std::vector<FloorplanPoint> points;
        for (const auto &r : refs) {
            auto p = pos.at(r);
            if (g.members.count(r)) {
                p.first += delta.first;
                p.second += delta.second;
            }
            points.push_back(p);
        }
        auto c = points_centroid(points), s = centroid.at(g.sheet);
        double radius =
            phase == "A"
                ? std::min(11., std::max(2., .5 * diag.at(g.sheet)))
                : std::min(40., std::max(11., std::sqrt(8 * area.at(g.sheet) / 3.141592653589793) -
                                                  diag.at(g.sheet)));
        return std::hypot(c.first - s.first, c.second - s.second) <= radius + eps;
    };
    auto foreign = [&](const std::string &anchor, const std::set<std::string> &members) {
        std::vector<Box4> out;
        auto sheet = ctx.by_ref.at(anchor).sheet;
        for (const auto &[r, p] : pos) {
            if (members.count(r) || !geometry.bbox_of.count(r) || !geometry.resolvable.count(r) ||
                side(r) != side(anchor) || som_refs.count(r))
                continue;
            const auto &part = ctx.by_ref.at(r);
            bool df40 = part.sheet.size() > 5 && part.sheet.rfind("som_j", 0) == 0 &&
                        std::all_of(part.sheet.begin() + 5, part.sheet.end(),
                                    [](char c) { return c >= '0' && c <= '9'; });
            if (df40 || pins(r) >= board_decision_policy::df40_min_pins || part.footprint.find("Fiducial") != std::string::npos ||
                is_testpoint_ref(r) || (part.sheet == sheet && cp(r)))
                continue;
            out.push_back(box(r, p));
        }
        return out;
    };
    auto clearance = [](Box4 b, const std::vector<Box4> &boxes) {
        double best = std::numeric_limits<double>::infinity();
        for (const auto &f : boxes)
            best = std::min(best, rect_gap(b, f));
        return best;
    };
    for (auto &g : groups)
        g.deficit =
            g.target - clearance(box(g.anchor, pos.at(g.anchor)), foreign(g.anchor, g.members));
    std::stable_sort(groups.begin(), groups.end(), [](const auto &a, const auto &b) {
        return std::make_pair(-a.deficit, a.anchor) < std::make_pair(-b.deficit, b.anchor);
    });
    std::vector<std::string> guards;
    for (const auto &[r, p] : pos) {
        (void)p;
        if (!geometry.bbox_of.count(r) || !geometry.resolvable.count(r) || som_refs.count(r))
            continue;
        int n = pins(r);
        if (n >= 3 && n < board_decision_policy::df40_min_pins && need(n) > pc + 1e-9)
            guards.push_back(r);
    }
    auto free = [&](const Group &g, FloorplanPoint delta) {
        for (const auto &r : g.members) {
            auto old = pos.at(r);
            auto b = box(r, {old.first + delta.first, old.second + delta.second});
            if (!grid(r).free(grow_rect(b, pc / 2)))
                return false;
            for (const auto &s : guards) {
                if (g.members.count(s) || side(r) != side(s))
                    continue;
                if ((cp(r) && ctx.by_ref.at(r).sheet == ctx.by_ref.at(s).sheet) ||
                    is_testpoint_ref(r))
                    continue;
                if (rect_gap(b, box(s, pos.at(s))) < need(pins(s)) - eps)
                    return false;
            }
            if (pins(r) >= 3 && need(pins(r)) > pc + 1e-9) {
                auto fb = foreign(r, g.members);
                double old_clear = clearance(box(r, old), fb), new_clear = clearance(b, fb);
                if (new_clear < std::min(need(pins(r)), old_clear) - eps)
                    return false;
            }
        }
        return true;
    };
    auto snap = [&](const Group &g, FloorplanPoint delta) {
        auto p = pos.at(g.anchor);
        return FloorplanPoint{
            py_round(ctx.fixed_grid(25 + p.first + delta.first, "breathe_anchor_grid") - 25 - p.first, 4),
            py_round(ctx.fixed_grid(25 + p.second + delta.second, "breathe_anchor_grid") - 25 - p.second, 4)};
    };
    for (const auto &g : groups) {
        auto fb = foreign(g.anchor, g.members);
        auto mb = box(g.anchor, pos.at(g.anchor));
        double cur = clearance(mb, fb);
        if (cur >= g.target - eps)
            continue;
        double reach = g.target - cur + 2;
        std::vector<FloorplanPoint> directions;
        if (!fb.empty()) {
            auto closest = *std::min_element(fb.begin(), fb.end(), [&](Box4 a, Box4 b) {
                return rect_gap(mb, a) < rect_gap(mb, b);
            });
            auto mc = rect_center(mb), fc = rect_center(closest);
            double x = mc.first - fc.first, y = mc.second - fc.second, n = std::hypot(x, y);
            if (n > 1e-6)
                directions.push_back({x / n, y / n});
        }
        if (phase != "A") {
            double r2 = std::sqrt(.5);
            for (auto d : std::vector<FloorplanPoint>{
                     {0, -1}, {0, 1}, {1, 0}, {-1, 0}, {r2, -r2}, {-r2, -r2}, {r2, r2}, {-r2, r2}})
                directions.push_back(d);
        }
        for (const auto &r : g.members)
            grid(r).stamp(grow_rect(box(r, pos.at(r)), pc / 2), 0);
        FloorplanPoint best{0, 0};
        double best_clear = cur;
        bool won = false;
        for (auto d : directions) {
            for (int k = 1; k <= static_cast<int>(reach / step) + 1; ++k) {
                FloorplanPoint delta{d.first * k * step, d.second * k * step};
                if (!leash(g, delta) || !free(g, delta))
                    break;
                auto p = pos.at(g.anchor);
                double trial =
                    clearance(box(g.anchor, {p.first + delta.first, p.second + delta.second}), fb);
                if (trial > best_clear + eps) {
                    best_clear = trial;
                    best = delta;
                }
                if (trial >= g.target - eps) {
                    best = delta;
                    won = true;
                    break;
                }
            }
            if (won)
                break;
        }
        if (best != FloorplanPoint{0, 0}) {
            auto snapped = snap(g, best);
            std::optional<FloorplanPoint> commit;
            if (free(g, snapped) && leash(g, snapped))
                commit = snapped;
            else {
                double n = std::hypot(best.first, best.second);
                if (n > 1e-6)
                    for (int k = static_cast<int>(n / step); k > 0; --k) {
                        FloorplanPoint d{best.first / n * k * step, best.second / n * k * step};
                        d = snap(g, d);
                        if (free(g, d) && leash(g, d)) {
                            commit = d;
                            break;
                        }
                    }
            }
            if (commit && *commit != FloorplanPoint{0, 0})
                for (const auto &r : g.members) {
                    auto p = pos.at(r);
                    pos[r] = {py_round(p.first + commit->first, 4),
                              py_round(p.second + commit->second, 4)};
                }
        }
        for (const auto &r : g.members)
            grid(r).stamp(grow_rect(box(r, pos.at(r)), pc / 2), 1);
    }
    for (const auto &[sheet, refs] : by_sheet) {
        if (refs.size() <= 3)
            continue;
        std::vector<Box4> boxes;
        for (const auto &r : refs)
            boxes.push_back(box(r, pos.at(r)));
        auto b = *boxes_union(boxes);
        double d = (b.x1 - b.x0) * (b.y1 - b.y0) / area.at(sheet);
        if (d > std::max(8., disp.at(sheet)) + eps)
            for (const auto &r : refs)
                pos[r] = seed.at(r);
    }
}
} // namespace schgen::pcb_placement
