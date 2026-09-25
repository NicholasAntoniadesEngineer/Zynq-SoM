#include "pcb_placement_internal.hpp"

namespace schgen::pcb_placement {
PcbStageResult pack_zone(const Context &ctx, const Geometry &g,
                         const std::vector<std::string> &refs, double aspect,
                         const Rotations &rotations, const std::string &outer,
                         const std::set<std::string> &face,
                         const std::map<std::string, std::string> *sides) {
    const auto &so = sides ? *sides : g.side_of;
    double pc = ctx.clearance;
    std::vector<std::string> top, bottom;
    for (const auto &r : refs)
        (face.count(r) || so.at(r) == "bottom" ? bottom : top).push_back(r);
    auto rotation = [&](const std::string &r) {
        auto it = rotations.find(r);
        return it == rotations.end() ? 0 : it->second;
    };
    auto halo = [&](const std::string &r) {
        return grow_rect(turn_box(g.bbox_of.at(r), rotation(r)), pc / 2);
    };
    auto fan = [&](const std::string &r) {
        auto np =
            static_cast<int>(pad_names_from_text(ctx.pool.at(g.resolvable.at(r))->bytes).size());
        double n = np >= 3 ? need(np) : pc;
        return std::make_pair(n > pc ? std::max(0., ctx.credit(n) - pc) : 0., passive(r, np));
    };
    auto items = [&](const std::vector<std::string> &rs, bool turned = true) {
        std::vector<ShelfItem> out;
        for (const auto &r : rs) {
            auto [extra, cp] = fan(r);
            out.push_back({r, turned ? halo(r) : grow_rect(g.bbox_of.at(r), pc / 2), extra, cp});
        }
        return out;
    };
    auto thru = [&](const std::string &r) {
        return has_thru_pads_from_text(ctx.pool.at(g.resolvable.at(r))->bytes);
    };
    auto offsets = [](const ShelfPacked &packed) {
        Offsets out;
        for (const auto &[r, x, y] : packed.placed)
            out[r] = {x, y};
        return out;
    };
    PcbStageResult result;
    if (!rotations.empty() && !outer.empty()) {
        std::vector<std::pair<std::string, bool>> conn;
        std::vector<std::string> rt, rb;
        for (const auto &r : top) {
            if (rotations.count(r))
                conn.push_back({r, false});
            else
                rt.push_back(r);
        }
        for (const auto &r : bottom) {
            if (rotations.count(r))
                conn.push_back({r, true});
            else
                rb.push_back(r);
        }
        bool horizontal = outer == "N" || outer == "S";
        std::sort(conn.begin(), conn.end(), [&](const auto &a, const auto &b) {
            auto x = halo(a.first), y = halo(b.first);
            double aw = horizontal ? x.x1 - x.x0 : x.y1 - x.y0,
                   bw = horizontal ? y.x1 - y.x0 : y.y1 - y.y0;
            return std::make_pair(-aw, a.first) < std::make_pair(-bw, b.first);
        });
        double cursor = zone_pad, depth = 0;
        for (const auto &[r, bot] : conn) {
            auto h = halo(r);
            double w = h.x1 - h.x0, height = h.y1 - h.y0;
            auto &dst = bot ? result.bottom : result.top;
            dst[r] = {py_round((horizontal ? cursor : zone_pad) - h.x0, 4),
                      py_round((horizontal ? zone_pad : cursor) - h.y0, 4)};
            cursor += (horizontal ? w : height) + pc;
            depth = std::max(depth, zone_pad + (horizontal ? height : w));
        }
        double behind = depth + 2, area = 0;
        for (const auto *list : {&rt, &rb})
            for (const auto &r : *list) {
                auto b = g.bbox_of.at(r);
                area += (b.x1 - b.x0 + pc) * (b.y1 - b.y0 + pc);
            }
        double target = connector_target_w(std::max(cursor, 8.), zone_pad, area, .62, aspect);
        auto t = shelf_pack(items(rt, false), target, {}, zone_pad);
        std::vector<ShelfOcc> blockers;
        for (const auto &[r, x, y] : t.placed)
            if (thru(r))
                blockers.push_back(
                    {offset_rect(grow_rect(g.bbox_of.at(r), pc / 2), x + (horizontal ? 0 : behind),
                                 y + (horizontal ? behind : 0)),
                     0, false});
        auto b = shelf_pack(items(rb, false), target, blockers, zone_pad);
        for (const auto &[r, x, y] : t.placed)
            result.top[r] = {py_round(x + (horizontal ? 0 : behind), 4),
                             py_round(y + (horizontal ? behind : 0), 4)};
        for (const auto &[r, x, y] : b.placed)
            result.bottom[r] = {py_round(x + (horizontal ? 0 : behind), 4),
                                py_round(y + (horizontal ? behind : 0), 4)};
        result.w = result.h = zone_pad;
        for (const auto *map : {&result.top, &result.bottom})
            for (const auto &[r, p] : *map) {
                auto b = turn_box(g.bbox_of.at(r), rotation(r));
                result.w = std::max(result.w, p.first + b.x1 + pc / 2);
                result.h = std::max(result.h, p.second + b.y1 + pc / 2);
            }
        result.w = py_round(result.w + zone_pad, 4);
        result.h = py_round(result.h + zone_pad, 4);
        if (outer == "S" || outer == "E")
            for (auto *map : {&result.top, &result.bottom})
                for (auto &[r, p] : *map) {
                    auto b = turn_box(g.bbox_of.at(r), rotation(r));
                    if (outer == "S")
                        p.second = py_round(result.h - (p.second + b.y1) - b.y0, 4);
                    else
                        p.first = py_round(result.w - (p.first + b.x1) - b.x0, 4);
                }
        return result;
    }
    double area = 0;
    for (const auto &r : refs) {
        auto b = g.bbox_of.at(r);
        area += (b.x1 - b.x0 + pc) * (b.y1 - b.y0 + pc);
    }
    double target = zone_target_w(area, .62, aspect, 8.);
    std::vector<std::string> buttons;
    for (const auto &r : top)
        if (std::filesystem::path(ctx.pool.at(g.resolvable.at(r))->source)
                .stem()
                .string()
                .find("TS-1187A") != std::string::npos)
            buttons.push_back(r);
    double tw, th;
    if (buttons.size() >= 2) {
        std::vector<std::tuple<std::string, double, double, double, double>> rows;
        for (const auto &r : buttons) {
            auto b = g.bbox_of.at(r);
            rows.emplace_back(r, b.x0, b.y0, b.x1, b.y1);
        }
        auto grid = grid_controls(rows, target, 2, zone_pad, pc);
        std::vector<ShelfOcc> blockers;
        for (auto b : grid.occ)
            blockers.push_back({b, 0, false});
        for (const auto &[r, x, y] : grid.offs) {
            result.top[r] = {x, y};
            int n = static_cast<int>(
                pad_names_from_text(ctx.pool.at(g.resolvable.at(r))->bytes).size());
            blockers.push_back({offset_rect(grow_rect(g.bbox_of.at(r), pc / 2), x, y),
                                std::max(0., ctx.credit(n >= 3 ? need(n) : pc) - pc),
                                passive(r, n)});
        }
        std::vector<std::string> rest;
        for (const auto &r : top)
            if (std::find(buttons.begin(), buttons.end(), r) == buttons.end())
                rest.push_back(r);
        auto pack = shelf_pack(items(rest), target, blockers, zone_pad);
        for (const auto &[r, p] : offsets(pack))
            result.top[r] = p;
        tw = std::max(grid.packed_w, pack.packed_w);
        th = std::max(grid.packed_h, pack.packed_h);
    } else {
        auto pack = shelf_pack(items(top), target, {}, zone_pad);
        result.top = offsets(pack);
        tw = pack.packed_w;
        th = pack.packed_h;
    }
    std::vector<ShelfOcc> blockers;
    for (const auto &r : top)
        if (thru(r)) {
            auto p = result.top.at(r);
            blockers.push_back(
                {offset_rect(grow_rect(g.bbox_of.at(r), pc / 2), p.first, p.second), 0, false});
        }
    auto pack = shelf_pack(items(bottom), target, blockers, zone_pad);
    result.bottom = offsets(pack);
    result.w = py_round(std::max(tw, pack.packed_w), 4);
    result.h = py_round(std::max(th, pack.packed_h), 4);
    return result;
}
} // namespace schgen::pcb_placement
