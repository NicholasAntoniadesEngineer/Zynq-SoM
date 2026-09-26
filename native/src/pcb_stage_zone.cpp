#include "pcb_stage_internal.hpp"

namespace schgen::pcb_stage {
PcbStageResult Engine::proximity_zone() {
    const auto &structures = optional(in.contract, "structures").array_value;
    std::string anchor;
    for (const auto &s : structures)
        if (text(s, "type") == "same_side") {
            auto ics = strings(s, "ics");
            if (!ics.empty()) {
                anchor = bref(ics.front());
                break;
            }
        }
    if (anchor.empty())
        for (const auto &s : structures)
            if (text(s, "type") == "proximity") {
                anchor = bref(text(s, "anchor"));
                break;
            }
    if (anchor.empty())
        throw PcbZoneInfeasible(in.sheet + ": proximity contract has no resolvable anchor");
    std::set<std::string> anchors;
    bool star = true;
    for (const auto &s : structures)
        if (text(s, "type") == "proximity") {
            auto a = bref(text(s, "anchor"));
            if (!a.empty())
                anchors.insert(a);
            for (const auto &mf : optional(s, "min_from").array_value) {
                auto m = bref(text(mf, "part"));
                if (!m.empty() && m != a)
                    star = false;
            }
        }
    auto parts =
        in.pilot && star && anchors.size() <= 1 ? proximity_cluster(anchor) : solve_contract();
    std::vector<Box4> all;
    for (const auto &p : parts) {
        auto b = values(pads(p));
        all.insert(all.end(), b.begin(), b.end());
    }
    auto ext = boxes_union(all);
    if (!ext)
        throw PcbZoneInfeasible("proximity contract has no pad geometry");
    auto placed = shifted(parts, zone_pad - ext->x0, zone_pad - ext->y0);
    std::set<std::string> media;
    for (const auto &s : structures)
        if (text(s, "type") == "proximity" && !strings(s, "anchor_pins").empty() &&
            bref(text(s, "anchor")) == anchor)
            for (const auto &lib : strings(s, "members")) {
                auto b = bref(lib);
                if (!b.empty())
                    media.insert(b);
            }
    placed = face(placed, media, true);
    PcbStageResult result;
    std::tie(result.w, result.h) = row_extent(placed);
    for (const auto &p : placed) {
        result.top[p.ref] = {p.x, p.y};
        if (std::abs(p.rot) > 1e-6 && !connector(*p.mod))
            result.rotations[p.ref] = normalize(p.rot);
    }
    std::vector<std::string> leftovers;
    for (const auto &r : in.refs)
        if (!find(placed, r))
            leftovers.push_back(r);
    double gx = 0, gy = 0;
    if (!leftovers.empty()) {
        double row_bottom = extent(placed).y1, row_top = extent(placed).y0;
        std::vector<double> conn_low{row_top}, conn_high{row_bottom};
        if (!in.outer_dir.empty())
            for (const auto &p : placed)
                if (connector(*p.mod)) {
                    auto b = body(p);
                    double n = credit(need(static_cast<int>(pads(p.mod).size())));
                    conn_low.push_back(b.y0 - n);
                    conn_high.push_back(b.y1 + n);
                }
        auto bands = leftover(leftovers, std::max(result.w - 2 * zone_pad, 8.));
        double bx = 0, by;
        if (in.outer_dir != "S")
            by = *std::max_element(conn_high.begin(), conn_high.end()) + 2 - zone_pad;
        else
            by = *std::min_element(conn_low.begin(), conn_low.end()) - 2 -
                 std::max(bands.first.packed_h, bands.second.packed_h) - zone_pad;
        if (in.outer_dir == "W") {
            std::vector<double> faces;
            for (const auto &p : placed)
                if (connector(*p.mod))
                    faces.push_back(pinbox(pads(p), {}).x0);
            if (!faces.empty())
                bx = *std::min_element(faces.begin(), faces.end()) + seat_slide();
        }
        for (const auto &[r, x, y] : bands.first.placed)
            result.top[r] = {py_round(x + bx, 4), py_round(y + by, 4)};
        for (const auto &[r, x, y] : bands.second.placed)
            result.bottom[r] = {py_round(x + bx, 4), py_round(y + by, 4)};
        double minx = std::numeric_limits<double>::infinity(), miny = minx;
        for (const auto *offsets : {&result.top, &result.bottom})
            for (const auto &[r, p] : *offsets) {
                (void)r;
                minx = std::min(minx, p.first);
                miny = std::min(miny, p.second);
            }
        gx = minx < zone_pad ? zone_pad - minx : 0;
        gy = miny < zone_pad ? zone_pad - miny : 0;
        if (gx || gy)
            for (auto *offsets : {&result.top, &result.bottom})
                for (auto &[r, p] : *offsets) {
                    (void)r;
                    p = {py_round(p.first + gx, 4), py_round(p.second + gy, 4)};
                }
        double maxx = extent(placed).x1 + gx, maxy = extent(placed).y1 + gy;
        if (!bands.first.placed.empty() || !bands.second.placed.empty()) {
            maxx =
                std::max({maxx, bx + gx + bands.first.packed_w, bx + gx + bands.second.packed_w});
            maxy =
                std::max({maxy, by + gy + bands.first.packed_h, by + gy + bands.second.packed_h});
        }
        result.w = py_round(maxx + zone_pad, 4);
        result.h = py_round(maxy + zone_pad, 4);
    }
    if (auto ov = direction(in.outer_dir)) {
        auto [vx, vy] = *ov;
        std::vector<double> faces;
        for (const auto &p : placed)
            if (connector(*p.mod)) {
                auto b = pinbox(pads(p), {});
                faces.push_back(vx > 0   ? b.x1 + gx
                                : vx < 0 ? b.x0 + gx
                                : vy > 0 ? b.y1 + gy
                                         : b.y0 + gy);
            }
        if (!faces.empty()) {
            if (vx > 0)
                result.w = *std::max_element(faces.begin(), faces.end()) + .4;
            else if (vy > 0)
                result.h = *std::max_element(faces.begin(), faces.end()) + .4;
            else {
                double d = .4 - *std::min_element(faces.begin(), faces.end());
                for (auto *offsets : {&result.top, &result.bottom})
                    for (auto &[r, p] : *offsets) {
                        (void)r;
                        if (vx < 0)
                            p.first = py_round(p.first + d, 4);
                        else
                            p.second = py_round(p.second + d, 4);
                    }
                if (vx < 0)
                    result.w += d;
                else
                    result.h += d;
            }
        }
    }
    result.w = py_round(result.w, 4);
    result.h = py_round(result.h, 4);
    return result;
}
} // namespace schgen::pcb_stage

namespace schgen {
PcbStageRefitResult refit_pcb_stage_facing_accounted(
    const PcbStageInput &in, const FloorplanOffsets &xy, const FloorplanRotations &rotations,
    FloorplanPoint downstream,
    const std::map<std::string, std::vector<std::pair<std::string, std::string>>> &nets,
    const std::map<std::string, std::vector<std::tuple<double, double, std::string>>> &foreign) {
    using namespace pcb_stage;
    Engine e(in);
    auto finish = [&](std::optional<PcbStageRefitPoses> poses = std::nullopt) {
        return PcbStageRefitResult{std::move(poses), std::move(e.quantization), std::move(e.events)};
    };
    auto output = e.output_refs();
    std::vector<std::string> present;
    for (const auto &r : output)
        if (xy.count(r))
            present.push_back(r);
    if (present.empty())
        return finish();
    Parts parts;
    for (const auto &[r, p] : xy) {
        if (!in.footprints.count(r))
            return finish();
        auto it = rotations.find(r);
        parts.push_back(
            e.part(r, it == rotations.end() ? 0 : normalize(it->second), p.first, p.second));
    }
    auto turned = e.turn(parts, 180, false, true, true);
    auto gate = [&](const Parts &ps) {
        std::vector<FloorplanPoint> all, own;
        for (const auto &p : ps) {
            all.emplace_back(p.x, p.y);
            if (output.count(p.ref))
                own.emplace_back(p.x, p.y);
        }
        auto a = points_centroid(all), b = points_centroid(own);
        return facing_align_dot(a.first, a.second, b.first, b.second, downstream.first - a.first,
                                downstream.second - a.second) > 0;
    };
    bool now = gate(parts), next = gate(turned);
    if (now && !next)
        return finish();
    auto air = [&](const Parts &ps) {
        double total = 0;
        for (const auto &[net, pts] : foreign) {
            std::vector<RatsnestPad> points;
            for (const auto &[x, y, s] : pts)
                points.emplace_back(x, y, "", s);
            auto ni = nets.find(net);
            if (ni != nets.end())
                for (const auto &[r, pn] : ni->second) {
                    auto part = find(ps, r);
                    if (!part)
                        continue;
                    auto pb = e.pads(*part);
                    auto b = std::find_if(pb.begin(), pb.end(),
                                          [pin = pn](const auto &p) { return p.first == pin; });
                    if (b == pb.end())
                        continue;
                    // Match Python's center-then-translate arithmetic exactly.
                    const auto &rel = at(e.pads(part->mod, part->rot), pn);
                    points.emplace_back(py_round(part->x + (rel.x0 + rel.x1) / 2, 3),
                                        py_round(part->y + (rel.y0 + rel.y1) / 2, 3), r, in.sheet);
                }
            RatsnestNets nn{{net, points}};
            auto edges = ratsnest_mst(nn);
            for (const auto &[a, b] : edges.at(net))
                if (std::get<3>(points[a]) != std::get<3>(points[b]))
                    total += hypot_xy(std::get<0>(points[a]), std::get<1>(points[a]),
                                      std::get<0>(points[b]), std::get<1>(points[b]));
        }
        return total;
    };
    if (!(!now && next) && !(air(turned) < air(parts) - 1e-6))
        return finish();
    std::map<std::string, std::tuple<double, double, double>> out;
    for (const auto &p : turned)
        out[p.ref] = {p.x, p.y, p.rot};
    return finish(std::move(out));
}
std::optional<std::map<std::string, std::tuple<double, double, double>>> refit_pcb_stage_facing(
    const PcbStageInput &in, const FloorplanOffsets &xy, const FloorplanRotations &rotations,
    FloorplanPoint downstream,
    const std::map<std::string, std::vector<std::pair<std::string, std::string>>> &nets,
    const std::map<std::string, std::vector<std::tuple<double, double, std::string>>> &foreign) {
    return refit_pcb_stage_facing_accounted(in, xy, rotations, downstream, nets, foreign).poses;
}
} // namespace schgen
