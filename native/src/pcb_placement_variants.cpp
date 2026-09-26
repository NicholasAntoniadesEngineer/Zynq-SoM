#include "pcb_placement_internal.hpp"

namespace schgen::pcb_placement {
bool mirror_holds(const Context &ctx, const Geometry &g, const std::string &sheet,
                  const Shape &shape) {
    if (!ctx.in.contracts.count(sheet))
        return true;
    auto input = ctx.stage_input(sheet, g);
    Engine engine(input);
    Offsets offsets = shape.top_off;
    offsets.insert(shape.bot_off.begin(), shape.bot_off.end());
    auto pads = [&](const std::string &lib) -> NamedBoxes {
        auto br = input.board_refs.find(lib);
        if (br == input.board_refs.end())
            return {};
        const auto &r = br->second;
        auto p = offsets.find(r);
        if (p == offsets.end())
            return {};
        auto fp = input.footprints.find(r);
        if (fp == input.footprints.end())
            return {};
        auto mirror = shape.mirror.find(r);
        auto mod = mirror == shape.mirror.end() ? fp->second : ctx.pool.at(mirror->second);
        double rot = 0;
        auto base = g.conn_rot.find(r);
        if (base != g.conn_rot.end())
            rot = base->second;
        auto extra = shape.extra_rot.find(r);
        if (extra != shape.extra_rot.end())
            rot += extra->second;
        return engine.pads({r, mod, normalize(rot), p->second.first, p->second.second});
    };
    for (const auto &s : optional(input.contract, "structures").array_value)
        if (text(s, "type") == "proximity") {
            auto a = pads(text(s, "anchor"));
            if (a.empty())
                continue;
            for (const auto &lib : strings(s, "members")) {
                auto m = pads(lib);
                if (m.empty())
                    continue;
                if (distance(a, m, strings(s, "anchor_pins")) > number(s, "max_mm"))
                    return false;
                for (const auto &mf : optional(s, "min_from").array_value) {
                    auto b = pads(text(mf, "part"));
                    if (b.empty())
                        continue;
                    auto pin = text(mf, "pin");
                    if (distance(b, m,
                                 pin.empty()
                                     ? std::vector<std::string>{}
                                     : std::vector<std::string>{pin}) < number(mf, "min_mm"))
                        return false;
                }
            }
        }
    return true;
}
std::optional<Shape> member_mirror(const Context &ctx, const Geometry &g, const std::string &sheet,
                                   const PcbStageResult &p, const Rotations &connectors) {
    Shape s;
    s.w = placement_variant_dimension_precision4dp(p.w, &ctx.quantization);
    s.h = placement_variant_dimension_precision4dp(p.h, &ctx.quantization);
    s.top_off = p.top;
    s.bot_off = p.bottom;
    s.tag = "mirror";
    std::vector<std::pair<std::string, Box4>> members;
    std::vector<Box4> boxes, conn_boxes;
    for (const auto *offsets : {&p.top, &p.bottom})
        for (const auto &[r, xy] : *offsets) {
            auto rot = p.rotations.find(r);
            auto b = offset_turned_box(g.bbox_of.at(r), rot == p.rotations.end() ? 0 : rot->second,
                                       xy.first, xy.second);
            if (!connectors.count(r)) {
                members.push_back({r, b});
                boxes.push_back(b);
            } else {
                conn_boxes.push_back(
                    offset_turned_box(g.bbox_of.at(r), connectors.at(r), xy.first, xy.second));
                s.extra_rot[r] = 0;
            }
        }
    if (members.empty())
        return {};
    auto center = rect_center(*boxes_union(boxes));
    for (const auto &[r, b] : members) {
        Box4 next{placement_member_box_precision4dp(2 * center.first - b.x1, &ctx.quantization), placement_member_box_precision4dp(2 * center.second - b.y1, &ctx.quantization),
                  placement_member_box_precision4dp(2 * center.first - b.x0, &ctx.quantization), placement_member_box_precision4dp(2 * center.second - b.y0, &ctx.quantization)};
        if (next.x0 < -1e-6 || next.y0 < -1e-6 || next.x1 > p.w + 1e-6 || next.y1 > p.h + 1e-6)
            return {};
        for (const auto &c : conn_boxes)
            if (boxes_overlap(next, c, ctx.clearance))
                return {};
        auto &xy = s.top_off.count(r) ? s.top_off.at(r) : s.bot_off.at(r);
        xy = {placement_member_pose_precision4dp(2 * center.first - xy.first, &ctx.quantization), placement_member_pose_precision4dp(2 * center.second - xy.second, &ctx.quantization)};
        auto rot = p.rotations.find(r);
        s.extra_rot[r] = normalize((rot == p.rotations.end() ? 0 : rot->second) + 180);
    }
    if (!mirror_holds(ctx, g, sheet, s))
        return {};
    return s;
}
std::vector<Shape> bottom_shapes(Context &ctx, const Geometry &g, const std::string &sheet,
                                 const std::set<std::string> &face,
                                 const std::optional<PcbStageResult> &tmpl,
                                 const std::set<std::string> &members,
                                 std::vector<std::string> &events) {
    auto mirror = [&](PcbStageResult p, const std::string &tag) {
        Shape s;
        s.w = p.w;
        s.h = p.h;
        s.tag = tag;
        s.side = "bottom";
        for (const auto &[r, xy] : p.top) {
            if (face.count(r))
                throw PcbZoneInfeasible(
                    "bottom eligibility retained a face-top part in its primary pack: " + r);
            s.top_off[r] = {placement_bottom_pose_precision4dp(p.w - xy.first, &ctx.quantization), xy.second};
            double rot = p.rotations.count(r) ? p.rotations.at(r) : 0;
            s.extra_rot[r] = normalize(180 - rot);
            auto key = g.resolvable.at(r), mk = "@mirror/" + key;
            auto fp = ctx.pool.at(key);
            auto doc = mirrored_footprint(fp->document);
            auto parent = std::filesystem::path(fp->source).parent_path().filename().string();
            if (parent.size() >= 7 && parent.compare(parent.size() - 7, 7, ".pretty") == 0)
                parent.resize(parent.size() - 7);
            auto path =
                (std::filesystem::path(".mirrored_fp") /
                 (parent + "__" + std::filesystem::path(fp->source).stem().string() + ".kicad_mod"))
                    .string();
            ctx.pool[mk] = pcb_check_footprint(path, sexpr_dumps(doc) + "\n", doc);
            s.mirror[r] = mk;
        }
        for (const auto &[r, xy] : p.bottom) {
            double rot = p.rotations.count(r) ? p.rotations.at(r) : 0;
            auto cb = turn_box(g.bbox_of.at(r), rot);
            s.bot_off[r] = mirror_offset_x(xy.first, xy.second, cb, p.w);
            if (p.rotations.count(r))
                s.extra_rot[r] = rot;
        }
        return s;
    };
    if (tmpl) {
        auto p = *tmpl;
        std::vector<std::string> lifted;
        for (const auto &[r, xy] : p.top) {
            (void)xy;
            if (face.count(r)) {
                if (members.count(r)) {
                    events.push_back("bottom_variant_contract_reject");
                    return {};
                }
                lifted.push_back(r);
            }
        }
        if (!lifted.empty()) {
            std::vector<ShelfOcc> blockers;
            auto halo = [&](const std::string &r, FloorplanPoint xy) {
                return grow_rect(offset_turned_box(g.bbox_of.at(r),
                                                   p.rotations.count(r) ? p.rotations.at(r) : 0,
                                                   xy.first, xy.second),
                                 ctx.clearance / 2);
            };
            auto meta = [&](const std::string &r) {
                int n = static_cast<int>(
                    pad_names_from_text(ctx.pool.at(g.resolvable.at(r))->bytes).size());
                double floor = n >= 3 ? need(n) : ctx.clearance;
                return std::make_pair(
                    floor > ctx.clearance ? std::max(0., ctx.credit(floor) - ctx.clearance) : 0.,
                    passive(r, n));
            };
            for (const auto &r : lifted)
                p.top.erase(r);
            for (const auto &[r, xy] : p.top)
                if (has_thru_pads_from_text(ctx.pool.at(g.resolvable.at(r))->bytes))
                    blockers.push_back({halo(r, xy), 0, false});
            for (const auto &[r, xy] : p.bottom) {
                auto [extra, cp] = meta(r);
                blockers.push_back({halo(r, xy), extra, cp});
            }
            std::vector<ShelfItem> items;
            for (const auto &r : lifted) {
                auto [extra, cp] = meta(r);
                items.push_back({r, halo(r, {0, 0}), extra, cp});
            }
            auto pack = shelf_pack(items, std::max(0., p.w - 2 * zone_pad), blockers, zone_pad);
            for (const auto &[r, x, y] : pack.placed)
                p.bottom[r] = {x, y};
            double mx = 0, my = 0;
            for (const auto &[r, xy] : p.bottom) {
                auto b = halo(r, xy);
                mx = std::max(mx, b.x1);
                my = std::max(my, b.y1);
            }
            p.w = placement_lift_extent_precision4dp(std::max(p.w, mx + zone_pad), &ctx.quantization);
            p.h = placement_lift_extent_precision4dp(std::max(p.h, my + zone_pad), &ctx.quantization);
        }
        auto shape = mirror(p, "bottom");
        if (mirror_holds(ctx, g, sheet, shape))
            return {shape};
        events.push_back("bottom_variant_contract_reject");
        return {};
    }
    std::set<FloorplanPoint> seen;
    std::vector<Shape> result;
    auto all_top = g.side_of;
    for (const auto &r : g.refs_by_sheet.at(sheet))
        all_top[r] = "top";
    for (bool split : {false, true})
        for (double aspect : {1., 2.2, 1., .45}) {
            auto p = pack_zone(ctx, g, g.refs_by_sheet.at(sheet), aspect, {}, "", face,
                               split ? nullptr : &all_top);
            if (!seen.insert({placement_shape_key_precision4dp(p.w, &ctx.quantization), placement_shape_key_precision4dp(p.h, &ctx.quantization)}).second)
                continue;
            std::string a = aspect == 1 ? "1" : aspect == 2.2 ? "2.2" : "0.45";
            result.push_back(mirror(p, (split ? "bottom-split-a" : "bottom-a") + a));
        }
    return result;
}
} // namespace schgen::pcb_placement
