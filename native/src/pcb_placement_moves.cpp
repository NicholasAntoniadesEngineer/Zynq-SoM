#include "pcb_placement_internal.hpp"

namespace schgen::pcb_placement {
namespace {
bool hit(Box4 b, const std::vector<Box4> &boxes) {
    return std::any_of(boxes.begin(), boxes.end(),
                       [&](Box4 other) { return rects_intersect_open(b, other); });
}
using SubjectMap = std::map<std::string, std::pair<std::string, Box4>>;
} // namespace
void Placer::l4_pull() {
    double pc = ctx.clearance;
    auto center = FloorplanPoint{plan.som_x + plan.som.w / 2, plan.som_y + plan.som.h / 2};
    std::vector<Box4> through, corridors;
    std::map<std::string, Box4> bottom;
    SubjectMap subjects;
    for (const auto &[r, p] : pos) {
        if (side(r) == "top" && geometry.resolvable.count(r) &&
            has_thru_pads_from_text(mod(r)->bytes))
            through.push_back(grow_rect(box(r, p), pc));
        if (side(r) == "bottom" && geometry.bbox_of.count(r)) {
            bottom[r] = grow_rect(box(r, p), pc / 2);
            if (geometry.resolvable.count(r) && ctx.by_ref.count(r) && pins(r) >= 3)
                subjects[r] = {
                    ctx.by_ref.at(r).sheet,
                    grow_rect(box(r, p), std::max(0., ctx.credit(need(pins(r))) - pc / 2))};
        }
    }
    auto offset = ctx.in.floorplan.module_offset.value_or(FloorplanPoint{
        ctx.in.floorplan.project.module_offset[0], ctx.in.floorplan.project.module_offset[1]});
    if (pc > .5 || offset.first || offset.second)
        for (const auto &[r, j] : som_refs) {
            (void)j;
            if (geometry.resolvable.count(r) && pos.count(r))
                corridors.push_back(
                    pcb_escape_corridor_board(*mod(r), pos.at(r).first, pos.at(r).second, rot(r)));
        }
    for (const auto &[sheet, origin] : origins) {
        (void)origin;
        if (ctx.l4_exempt.count(sheet))
            continue;
        std::vector<std::string> movers;
        for (const auto &[r, p] : geometry.bot_off[sheet]) {
            (void)p;
            if (side(r) == "bottom" && pos.count(r) && !r.empty() &&
                (r[0] == 'R' || r[0] == 'C' || r[0] == 'L') && r.rfind("RJ", 0) != 0 &&
                r.rfind("LED", 0) != 0)
                movers.push_back(r);
        }
        if (movers.size() < 2)
            continue;
        std::vector<FloorplanPoint> points;
        for (const auto &r : movers)
            points.push_back(pos.at(r));
        auto c = points_centroid(points);
        double vx = center.first - c.first, vy = center.second - c.second,
               dist = hypot_xy(0, 0, vx, vy);
        if (dist < 1)
            continue;
        double ux = vx / dist, uy = vy / dist;
        std::set<std::string> moving(movers.begin(), movers.end());
        std::vector<Box4> others;
        for (const auto &[r, b] : bottom)
            if (!moving.count(r))
                others.push_back(b);
        others.insert(others.end(), corridors.begin(), corridors.end());
        for (const auto &[r, s] : subjects)
            if (s.first != sheet && !moving.count(r))
                others.push_back(s.second);
        std::vector<std::string> all;
        double area = 0;
        for (const auto *offsets : {&geometry.top_off[sheet], &geometry.bot_off[sheet]})
            for (const auto &[r, p] : *offsets) {
                (void)p;
                if (pos.count(r) && geometry.bbox_of.count(r)) {
                    all.push_back(r);
                    auto b = box(r, {0, 0});
                    area += (b.x1 - b.x0) * (b.y1 - b.y0);
                }
            }
        if (!area)
            area = 1;
        double chosen = 0;
        for (int k = static_cast<int>(std::min(dist, 40.)); k > 0; --k) {
            double shift = k;
            Offsets shifted;
            bool okay = true;
            for (const auto &r : movers) {
                auto old = pos.at(r);
                FloorplanPoint p{old.first + ux * shift, old.second + uy * shift};
                auto b = box(r, p);
                if (b.x0 < .6 || b.y0 < .6 || b.x1 > width - .6 || b.y1 > height - .6 ||
                    hit(grow_rect(b, pc / 2), others) || hit(grow_rect(b, pc / 2), through)) {
                    okay = false;
                    break;
                }
                shifted[r] = p;
            }
            if (!okay)
                continue;
            std::vector<Box4> boxes;
            for (const auto &r : all)
                boxes.push_back(box(r, shifted.count(r) ? shifted.at(r) : pos.at(r)));
            auto b = boxes_union(boxes);
            if (!b)
                continue;
            if ((b->x1 - b->x0) * (b->y1 - b->y0) / area > 5)
                continue;
            chosen = shift;
            break;
        }
        if (chosen > 0)
            for (const auto &r : movers) {
                auto p = pos.at(r);
                p = {py_round(p.first + ux * chosen, 4), py_round(p.second + uy * chosen, 4)};
                pos[r] = p;
                bottom[r] = grow_rect(box(r, p), pc / 2);
                auto s = subjects.find(r);
                if (s != subjects.end()) {
                    auto z = box(r, {0, 0});
                    double grow = (s->second.second.x1 - s->second.second.x0 - (z.x1 - z.x0)) / 2;
                    s->second.second = grow_rect(box(r, p), grow);
                }
            }
    }
}
void Placer::edge_seat() {
    for (const auto &[r, edge] : geometry.conn_edge) {
        if (!geometry.resolvable.count(r) || !pos.count(r))
            continue;
        std::vector<std::tuple<std::string, double, double, double, double, double>> rows;
        for (const auto &[name, type, x, y, rotation, w, h] : mod(r)->pads) {
            (void)name;
            rows.emplace_back(type, x, y, rotation, w, h);
        }
        std::vector<Box4> boxes;
        for (const auto &[type, x0, y0, x1, y1] : pad_boxes_local(rows, rot(r))) {
            (void)type;
            boxes.push_back({x0, y0, x1, y1});
        }
        auto b = boxes_union(boxes);
        if (!b)
            continue;
        auto p = pos.at(r);
        if (edge == "N")
            p.second = .4 - b->y0;
        else if (edge == "S")
            p.second = height - .4 - b->y1;
        else if (edge == "W")
            p.first = .4 - b->x0;
        else if (edge == "E")
            p.first = width - .4 - b->x1;
        pos[r] = {py_round(p.first, 4), py_round(p.second, 4)};
        grid_placed.insert(r);
    }
}
void Placer::refit() {
    std::map<std::string, std::vector<std::pair<std::string, std::string>>> net_pins;
    for (const auto &[key, n] : pin_net)
        if (!n.second.empty() && n.second.rfind("unconnected-", 0) != 0)
            net_pins[n.second].push_back(key);
    for (auto &[n, pins] : net_pins) {
        (void)n;
        std::sort(pins.begin(), pins.end());
    }
    PcbStageInput all;
    for (const auto &[r, key] : geometry.resolvable)
        all.footprints[r] = ctx.pool.at(key);
    Engine geometry_engine(all);
    for (const auto &[sheet, origin] : origins) {
        (void)origin;
        if (!ctx.wired.count(sheet) || !ctx.in.contracts.count(sheet))
            continue;
        const auto &contract = ctx.in.contracts.at(sheet);
        auto downstream = text(optional(contract, "external"), "downstream");
        if (downstream.empty())
            continue;
        std::vector<std::string> refs, down;
        for (const auto &r : geometry.refs_by_sheet[sheet])
            if (pos.count(r))
                refs.push_back(r);
        std::sort(refs.begin(), refs.end());
        for (const auto &r : geometry.refs_by_sheet[downstream])
            if (pos.count(r))
                down.push_back(r);
        if (refs.empty() || down.empty() ||
            std::any_of(refs.begin(), refs.end(),
                        [&](const auto &r) { return geometry.conn_rot.count(r); }))
            continue;
        std::vector<FloorplanPoint> dp;
        for (const auto &r : down)
            dp.push_back(pos.at(r));
        auto centroid = points_centroid(dp);
        std::set<std::string> own(refs.begin(), refs.end());
        std::map<std::string, std::vector<std::pair<std::string, std::string>>> own_pins;
        std::map<std::string, std::vector<std::tuple<double, double, std::string>>> foreign;
        for (const auto &[net, pins] : net_pins) {
            std::vector<std::pair<std::string, std::string>> own_net;
            for (const auto &p : pins)
                if (own.count(p.first))
                    own_net.push_back(p);
            if (own_net.empty())
                continue;
            own_pins[net] = own_net;
            auto &ext = foreign[net];
            for (const auto &[r, pin] : pins) {
                if (own.count(r) || !pos.count(r) || !geometry.resolvable.count(r))
                    continue;
                const auto &pb = geometry_engine.pads(mod(r), normalize(rot(r)));
                auto b = std::find_if(pb.begin(), pb.end(),
                                      [name = pin](const auto &p) { return p.first == name; });
                if (b == pb.end())
                    continue;
                auto p = pos.at(r);
                ext.emplace_back(py_round(p.first + (b->second.x0 + b->second.x1) / 2, 3),
                                 py_round(p.second + (b->second.y0 + b->second.y1) / 2, 3),
                                 ctx.by_ref.at(r).sheet);
            }
        }
        Offsets xy;
        for (const auto &r : refs)
            xy[r] = pos.at(r);
        auto result = refit_pcb_stage_facing_accounted(ctx.stage_input(sheet, geometry), xy, rotations,
                                             centroid, own_pins, foreign);
        checked_quantization_merge(ctx.quantization, result.quantization_engagements);
        out.placement_accounting.fallback_events.insert(out.placement_accounting.fallback_events.end(),
            result.fallback_events.begin(), result.fallback_events.end());
        out.fallback_events.insert(out.fallback_events.end(), result.fallback_events.begin(), result.fallback_events.end());
        if (result.poses)
            for (const auto &[r, p] : *result.poses) {
                pos[r] = {std::get<0>(p), std::get<1>(p)};
                rotations[r] = std::get<2>(p);
            }
    }
}
void Placer::reorder() {
    std::vector<ReorderPos> poses;
    std::vector<std::tuple<std::string, std::vector<std::string>>> sheets, pad_names;
    std::vector<std::tuple<std::string, std::vector<std::tuple<std::string, double, double>>>>
        local;
    std::vector<std::tuple<std::string, std::string, std::string, double, bool>> members;
    std::vector<std::tuple<std::string, double, double, double, double>> boxes;
    std::vector<std::tuple<std::string, std::string, std::string>> pn;
    std::vector<std::tuple<std::string, std::vector<std::pair<std::string, std::string>>>> nets;
    std::vector<std::string> resolved, skip, conn;
    for (const auto &[r, p] : pos) {
        poses.emplace_back(r, p.first, p.second);
        if (!geometry.resolvable.count(r))
            continue;
        auto names = pad_names_from_text(mod(r)->bytes);
        pad_names.emplace_back(r, names);
        std::vector<std::tuple<std::string, double, double>> pads;
        for (const auto &[name, type, x, y, angle, w, h] : mod(r)->pads) {
            (void)type;
            (void)angle;
            (void)w;
            (void)h;
            pads.emplace_back(name, x, y);
        }
        auto xy = inst_pad_xy(pads, 0, 0, rot(r), 3);
        std::vector<std::tuple<std::string, double, double>> unique;
        for (const auto &p : xy) {
            auto found = std::find_if(unique.begin(), unique.end(), [&](const auto &q) {
                return std::get<0>(q) == std::get<0>(p);
            });
            if (found == unique.end())
                unique.push_back(p);
            else
                *found = p;
        }
        local.emplace_back(r, unique);
    }
    for (const auto &[sheet, refs] : geometry.refs_by_sheet) {
        sheets.emplace_back(sheet, refs);
        for (const auto &r : refs)
            if (pos.count(r) && geometry.resolvable.count(r))
                members.emplace_back(
                    r, side(r), mod(r)->source, rot(r),
                    is_cluster_passive(r, pins(r), {"RS", "RJ", "RN", "LED"}, {"R", "C", "L"}));
    }
    for (const auto &[r, b] : geometry.bbox_of)
        boxes.emplace_back(r, b.x0, b.y0, b.x1, b.y1);
    for (const auto &[k, n] : pin_net)
        pn.emplace_back(k.first, k.second, n.second);
    for (const auto &[name, pins] : ctx.in.netlist) {
        std::vector<std::pair<std::string, std::string>> rows;
        for (const auto &p : pins)
            rows.emplace_back(p.ref, p.pin);
        nets.emplace_back(name, rows);
    }
    for (const auto &[r, k] : geometry.resolvable) {
        (void)k;
        resolved.push_back(r);
    }
    for (const auto &[r, v] : geometry.conn_rot) {
        (void)v;
        conn.push_back(r);
    }
    for (const auto &[s, p] : origins) {
        (void)p;
        if (ctx.wired.count(s) && ctx.in.contracts.count(s))
            skip.push_back(s);
    }
    auto result = reorder_interchangeable(poses, sheets, skip, conn, members, boxes, pad_names,
                                          local, pn, nets, resolved);
    for (const auto &[r, x, y] : std::get<0>(result))
        pos[r] = {x, y};
}
void Placer::evict() {
    std::vector<Box4> corridors, through;
    std::map<std::string, Box4> bottom;
    SubjectMap subjects;
    double pc = ctx.clearance;
    for (const auto &[r, j] : som_refs) {
        (void)j;
        if (pos.count(r) && geometry.resolvable.count(r))
            corridors.push_back(
                pcb_escape_corridor_board(*mod(r), ctx.corridor_grid(25, pos.at(r).first),
                                          ctx.corridor_grid(25, pos.at(r).second), rot(r)));
    }
    for (const auto &[r, p] : pos) {
        if (!geometry.bbox_of.count(r))
            continue;
        if (side(r) == "bottom")
            bottom[r] = box(r, p);
        else if (geometry.resolvable.count(r) && has_thru_pads_from_text(mod(r)->bytes))
            through.push_back(box(r, p));
    }
    for (const auto &[r, b] : bottom)
        if (geometry.resolvable.count(r) && ctx.by_ref.count(r) && pins(r) >= 3)
            subjects[r] = {ctx.by_ref.at(r).sheet,
                           grow_rect(b, std::max(0., ctx.credit(need(pins(r))) - pc))};
    for (auto &[ref, b] : bottom) {
        if (!hit(b, corridors))
            continue;
        std::vector<std::tuple<double, double, double>> exits;
        double m = pc / 2;
        for (const auto &c : corridors)
            if (rects_intersect_open(b, c)) {
                exits.emplace_back(c.x1 - b.x0 + m, c.x1 - b.x0 + m, 0);
                exits.emplace_back(b.x1 - c.x0 + m, -(b.x1 - c.x0 + m), 0);
                exits.emplace_back(c.y1 - b.y0 + m, 0, c.y1 - b.y0 + m);
                exits.emplace_back(b.y1 - c.y0 + m, 0, -(b.y1 - c.y0 + m));
            }
        std::sort(exits.begin(), exits.end());
        bool moved = false;
        for (const auto &[d, ex, ey] : exits) {
            (void)d;
            for (int k = 0; k < 9; ++k) {
                double sx = ex + (ex > 0   ? k
                                  : ex < 0 ? -k
                                           : 0),
                       sy = ey + (ey > 0   ? k
                                  : ey < 0 ? -k
                                           : 0);
                auto old = pos.at(ref);
                FloorplanPoint p{py_round(old.first + sx, 4), py_round(old.second + sy, 4)};
                auto next = box(ref, p);
                if (next.x0 < .6 || next.y0 < .6 || next.x1 > width - .6 || next.y1 > height - .6 ||
                    hit(next, corridors))
                    continue;
                auto grown = grow_rect(next, pc);
                bool blocked = hit(grown, through);
                for (const auto &[r, other] : bottom)
                    if (r != ref && rects_intersect_open(grown, other))
                        blocked = true;
                for (const auto &[r, s] : subjects)
                    if (r != ref && s.first != ctx.by_ref.at(ref).sheet &&
                        rects_intersect_open(grown, s.second))
                        blocked = true;
                if (blocked)
                    continue;
                pos[ref] = p;
                b = next;
                moved = true;
                break;
            }
            if (moved)
                break;
        }
        out.fallback_events.push_back(moved ? "corridor_evict_moved" : "corridor_stray_unmovable");
        out.placement_accounting.fallback_events.push_back(out.fallback_events.back());
    }
}
} // namespace schgen::pcb_placement
