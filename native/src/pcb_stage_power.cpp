#include "pcb_stage_internal.hpp"

namespace schgen::pcb_stage {
Parts Engine::buck(const std::string &ic, const std::vector<std::string> &hf,
                   const std::vector<std::string> &bulk, const std::vector<std::string> &cout,
                   const std::string &ind, const std::vector<std::string> &fb,
                   const std::string &boot, const std::string &vcc, const std::string &bias_r,
                   const std::string &bias_c, const std::string &rt,
                   const std::map<std::string, std::string> &pins) {
    if (hf.size() != 2)
        throw PcbZoneInfeasible("buck stage " + ic + ": two hot-loop caps required");
    for (int scale = 0; scale < 20; ++scale) {
        double pad = scale * .25, clr = clear + .2 + pad;
        auto anchor = part(ic);
        auto ib = pads(anchor);
        auto icb = body(anchor);
        Parts out{anchor};
        auto sw = at(ib, pins.at("sw"));
        auto inductor = beside(ind, 0, icb, "R", 1 + pad, (sw.y0 + sw.y1) / 2);
        out.push_back(inductor);
        auto il = body(inductor).x0;
        std::vector<FloorplanPoint> halves;
        for (const auto &r : cout) {
            auto b = body(part(r, 90));
            halves.emplace_back((b.x1 - b.x0) / 2, (b.y1 - b.y0) / 2);
        }
        if (!cout.empty()) {
            auto centers =
                cout_column_centers(at(pads(inductor), pins.at("ind_out")), pad, 1, clear, halves);
            for (std::size_t i = 0; i < cout.size(); ++i)
                out.push_back(part(cout[i], 90, centers[i].first, centers[i].second));
        }
        Parts hfs;
        for (std::size_t i = 0; i < 2; ++i) {
            auto target =
                pinbox(ib, {pins.at(i ? "vin2" : "vin1"), pins.at(i ? "pgnd2" : "pgnd1")});
            auto p = beside(hf[i], 0, target, i ? "U" : "D", clr);
            auto b = body(part(hf[i]));
            auto xy = hf_cap_pose(p.y, il, clear, (b.x1 - b.x0) / 2);
            p.x = xy.first;
            p.y = xy.second;
            hfs.push_back(p);
            out.push_back(p);
        }
        for (std::size_t i = 0; i < std::min<std::size_t>(2, bulk.size()); ++i) {
            auto b = body(part(bulk[i], 90));
            auto xy = bulk_cap_pose(hfs[i].x, body(hfs[i]), i ? "U" : "D", clr, (b.x1 - b.x0) / 2,
                                    (b.y1 - b.y0) / 2, il, clear);
            out.push_back(part(bulk[i], 90, xy.first, xy.second));
        }
        std::vector<Demand> demands;
        for (const auto &r : fb)
            demands.push_back({r, {pins.at("fb")}, 3, {pins.at("sw")}, 2});
        demands.push_back({vcc, {pins.at("vcc")}, 2, {}, 0});
        demands.push_back({boot, {pins.at("rboot"), pins.at("cboot")}, 2, {}, 0});
        demands.push_back({bias_c, {pins.at("bias")}, 3, {}, 0});
        demands.push_back({rt, {pins.at("rt")}, 3, {}, 0});
        demands.push_back({bias_r, {pins.at("bias")}, 20, {}, 0});
        auto seated = seat_all(demands, ib, icb, out, pad, true);
        out.insert(out.end(), seated.begin(), seated.end());
        if (!overlap(out))
            return out;
    }
    throw PcbZoneInfeasible("buck stage " + ic +
                            ": 20-scale widen exhausted with parts still overlapping");
}
Parts Engine::ldo(const std::string &ic, const std::string &cin, const std::string &cin_pin,
                  const std::string &cout, const std::string &cout_pin) {
    Parts out;
    for (int scale = 0; scale < 12; ++scale) {
        auto anchor = part(ic);
        auto ib = pads(anchor);
        out = {anchor};
        for (const auto &[ref, pin, sgn] : std::vector<std::tuple<std::string, std::string, int>>{
                 {cin, cin_pin, -1}, {cout, cout_pin, 1}}) {
            auto mod = part(ref).mod;
            const auto &first = pads(mod).front().second;
            double hx = (first.x1 - first.x0) / 2;
            const auto &b = at(ib, pin);
            double x = sgn < 0 ? b.x0 - .6 - scale * .25 - hx : b.x1 + .6 + scale * .25 + hx;
            out.push_back(part(ref, 0, py_round(x, 4), py_round((b.y0 + b.y1) / 2, 4)));
        }
        if (!overlap(out))
            return out;
    }
    return out;
}
PcbStageResult Engine::hot_zone() {
    const auto &structures = optional(in.contract, "structures").array_value;
    auto structure = [&](const std::string &type, const std::string &ic) -> const JsonNode & {
        for (const auto &s : structures)
            if (text(s, "type") == type && text(s, "ic") == ic)
                return s;
        throw PcbZoneInfeasible(in.sheet + ": missing " + type + " for " + ic);
    };
    auto resolve = [&](const std::string &lib) {
        auto b = bref(lib);
        if (b.empty())
            throw PcbZoneInfeasible(in.sheet + ": unresolvable stage member " + lib);
        return b;
    };
    auto refs = [&](const JsonNode &s, const std::string &key) {
        std::vector<std::string> result;
        for (const auto &lib : strings(s, key))
            result.push_back(resolve(lib));
        return result;
    };
    std::vector<std::string> bias;
    for (const auto &[r, v] : optional(in.contract, "roles").object_value)
        if (v.string_value == "bias_r")
            bias.push_back(r);
    std::size_t bias_index = 0;
    std::vector<Parts> stages;
    std::vector<bool> bucks;
    for (const auto &ic : strings(in.contract, "stage_order")) {
        auto b = resolve(ic);
        auto role = text(optional(in.contract, "roles"), ic);
        if (role == "buck_ic") {
            const auto &hl = structure("hot_loop", ic);
            const auto &sw = structure("sw_node", ic);
            const auto &fb = structure("fb_cluster", ic);
            const auto &boot = structure("boot", ic);
            const auto &vcc = structure("vcc_cap", ic);
            const auto &bc = structure("bias_cap", ic);
            const auto &rt = structure("rt_r", ic);
            const auto &bi = structure("bulk_in", ic);
            const JsonNode *bo = nullptr;
            for (const auto &s : structures)
                if (text(s, "type") == "bulk_out" && text(s, "ic") == ic)
                    bo = &s;
            const auto &pairs = field(hl, "pin_pairs").array_value;
            auto bp = strings(boot, "pins");
            if (pairs.size() != 2 || bp.size() != 2 || bias_index >= bias.size())
                throw PcbZoneInfeasible(in.sheet + ": incomplete buck recipe");
            auto p1 = strings(pairs[0]), p2 = strings(pairs[1]);
            if (p1.size() != 2 || p2.size() != 2)
                throw PcbZoneInfeasible("hot-loop pin pair malformed");
            std::map<std::string, std::string> pins{
                {"vin1", p1[0]},
                {"pgnd1", p1[1]},
                {"vin2", p2[0]},
                {"pgnd2", p2[1]},
                {"sw", text(sw, "sw_pin")},
                {"fb", text(fb, "fb_pin")},
                {"rboot", bp[0]},
                {"cboot", bp[1]},
                {"vcc", text(vcc, "pin")},
                {"bias", text(bc, "pin")},
                {"rt", text(rt, "pin")},
                {"ind_out", bo ? text(*bo, "inductor_out_pin") : "2"}};
            stages.push_back(buck(b, refs(hl, "caps"), refs(bi, "caps"),
                                  bo ? refs(*bo, "caps") : std::vector<std::string>{},
                                  resolve(text(sw, "inductor")), refs(fb, "members"),
                                  resolve(text(boot, "cap")), resolve(text(vcc, "cap")),
                                  resolve(bias[bias_index++]), resolve(text(bc, "cap")),
                                  resolve(text(rt, "resistor")), pins));
            bucks.push_back(true);
        } else if (role == "ldo_ic") {
            const auto &s = structure("ldo_stage", ic);
            stages.push_back(ldo(b, resolve(text(s, "cin")), text(s, "cin_pin"),
                                 resolve(text(s, "cout")), text(s, "cout_pin")));
            bucks.push_back(false);
        } else
            throw PcbZoneInfeasible(in.sheet + ": stage_order IC " + ic + " has unsupported role " +
                                    role);
    }
    if (stages.empty())
        throw PcbZoneInfeasible(in.sheet + ": hot-loop contract has no stages");
    std::map<std::string, std::size_t> stage_of;
    for (std::size_t i = 0; i < stages.size(); ++i)
        for (const auto &p : stages[i])
            stage_of[p.ref] = i;
    std::map<std::string, double> bound_of;
    std::map<std::string, std::vector<Attract>> att_of;
    std::map<std::string, std::vector<Repel>> rep_of;
    for (const auto &s : structures) {
        auto type = text(s, "type");
        std::string anchor, member_key, pin_key, bound_key;
        std::vector<Repel> rep;
        if (type == "proximity") {
            anchor = bref(text(s, "anchor"));
            member_key = "members";
            pin_key = "anchor_pins";
            bound_key = "max_mm";
        } else {
            anchor = bref(text(s, "ic"));
            if (type == "fb_cluster") {
                member_key = "members";
                pin_key = "fb_pin";
                bound_key = "max_to_fb_mm";
                auto mm = number(s, "min_to_own_sw_mm");
                if (mm > 0) {
                    if (!text(s, "own_sw_pin").empty())
                        rep.push_back({anchor, text(s, "own_sw_pin"), mm});
                    auto own = bref(text(s, "own_inductor"));
                    if (!own.empty())
                        rep.push_back({own, "", mm});
                }
            } else if (type == "rt_r") {
                member_key = "resistor";
                pin_key = "pin";
                bound_key = "max_pad_to_pin_mm";
            } else if (type == "bias_cap" || type == "vcc_cap") {
                member_key = "cap";
                pin_key = "pin";
                bound_key = "max_pad_to_pin_mm";
            } else if (type == "boot") {
                member_key = "cap";
                pin_key = "pins";
                bound_key = "max_pad_to_pin_mm";
            } else
                continue;
        }
        double bound = number(s, bound_key);
        if (anchor.empty() || bound <= 0)
            continue;
        for (const auto &lib : strings(s, member_key)) {
            auto b = bref(lib);
            if (!b.empty() && (!bound_of.count(b) || bound < bound_of.at(b))) {
                bound_of[b] = bound;
                att_of[b] = {{anchor, strings(s, pin_key), bound}};
                rep_of[b] = rep;
            }
        }
    }
    auto try_place = [&](const std::string &ref, const std::vector<Attract> &att,
                         const Parts &frame,
                         const std::vector<Repel> &reps) -> std::optional<Part> {
        std::vector<Repel> rep;
        for (const auto &r : reps)
            if (find(frame, r.ref))
                rep.push_back(r);
        for (double pad : {0., .5, 1.}) {
            auto c = candidates(ref, att, rep, frame, pad);
            if (!c.empty())
                return c.front();
        }
        return {};
    };
    for (const auto &s : structures)
        if (text(s, "type") == "proximity") {
            auto anchor = bref(text(s, "anchor"));
            auto si = stage_of.find(anchor);
            double bound = number(s, "max_mm");
            if (si == stage_of.end())
                throw PcbZoneInfeasible(in.sheet + ": proximity anchor is not a placed stage part");
            if (bound <= 0)
                throw PcbZoneInfeasible(in.sheet + ": proximity has no positive max_mm");
            std::vector<Attract> att{{anchor, strings(s, "anchor_pins"), bound}};
            for (const auto &lib : strings(s, "members")) {
                auto b = resolve(lib);
                if (stage_of.count(b))
                    continue;
                auto &stage = stages[si->second];
                auto got = try_place(b, att, stage, {});
                if (got) {
                    stage.push_back(*got);
                    stage_of[b] = si->second;
                    continue;
                }
                std::vector<std::string> ring;
                for (const auto &p : stage)
                    if (p.ref != anchor && bound_of[p.ref] >= bound && att_of.count(p.ref) &&
                        pads(p.mod).size() <= 2)
                        ring.push_back(p.ref);
                std::sort(ring.begin(), ring.end(), [&](const auto &a, const auto &c) {
                    return std::make_pair(-bound_of[a], a) < std::make_pair(-bound_of[c], c);
                });
                for (const auto &victim : ring) {
                    Parts frame;
                    for (const auto &p : stage)
                        if (p.ref != victim)
                            frame.push_back(p);
                    auto moved = try_place(b, att, frame, {});
                    if (!moved)
                        continue;
                    frame.push_back(*moved);
                    auto back = try_place(victim, att_of[victim], frame, rep_of[victim]);
                    if (!back)
                        continue;
                    frame.push_back(*back);
                    stage = std::move(frame);
                    stage_of[b] = si->second;
                    got = moved;
                    break;
                }
                if (!got)
                    throw PcbZoneInfeasible(
                        in.sheet + ": proximity member " + b +
                        " found no seat even after bound-priority displacement");
            }
        }
    auto mirror = [&](Parts ps) {
        auto e = extent(ps);
        auto c = rect_center(e);
        for (auto &p : ps) {
            auto old = boxes_span_center(values(pads(p.mod, p.rot)));
            auto nr = normalize(p.rot + 180);
            auto next = boxes_span_center(values(pads(p.mod, nr)));
            p.x = py_round(2 * c.first - (p.x + old.first) - next.first, 4);
            p.y = py_round(2 * c.second - (p.y + old.second) - next.second, 4);
            p.rot = nr;
        }
        return ps;
    };
    using Layout = std::vector<std::vector<std::size_t>>;
    struct LayoutChoice {
        Layout rows;
        std::set<std::size_t> mirror;
    };
    std::vector<std::size_t> seq, buck_ids, other_ids;
    for (std::size_t i = 0; i < stages.size(); ++i) {
        seq.push_back(i);
        (bucks[i] ? buck_ids : other_ids).push_back(i);
    }
    std::set<std::size_t> mirrors;
    if (buck_ids.size() >= 2)
        mirrors.insert(buck_ids[1]);
    std::vector<LayoutChoice> choices{{{seq}, mirrors}};
    if (!buck_ids.empty() && !other_ids.empty())
        choices.push_back({{buck_ids, other_ids}, mirrors});
    if (buck_ids.size() >= 2) {
        Layout rows;
        for (std::size_t i = 0; i + 1 < buck_ids.size(); ++i)
            rows.push_back({buck_ids[i]});
        auto last = other_ids;
        last.insert(last.begin(), buck_ids.back());
        rows.push_back(last);
        choices.push_back({rows, {}});
    }
    Layout single;
    for (auto i : seq)
        single.push_back({i});
    choices.push_back({single, {}});
    auto lay = [&](const LayoutChoice &choice) {
        auto frames = stages;
        for (auto i : choice.mirror)
            frames[i] = mirror(frames[i]);
        Parts out;
        double y = zone_pad;
        for (std::size_t ri = 0; ri < choice.rows.size(); ++ri) {
            const auto &row = choice.rows[ri];
            double miny = std::numeric_limits<double>::infinity();
            for (auto i : row)
                miny = std::min(miny, extent(frames[i]).y0);
            double dy = y - miny, x = zone_pad, bottom = y;
            for (std::size_t k = 0; k < row.size(); ++k) {
                auto i = row[k];
                auto b = extent(frames[i]);
                double dx = x - b.x0;
                auto ps = shifted(frames[i], dx, dy);
                out.insert(out.end(), ps.begin(), ps.end());
                bottom = std::max(bottom, b.y1 + dy);
                if (k + 1 < row.size())
                    x = b.x1 + dx + (bucks[i] && bucks[row[k + 1]] ? 6 : 1.2);
            }
            double gap = clear;
            if (ri + 1 < choice.rows.size() &&
                std::any_of(row.begin(), row.end(), [&](auto i) { return bucks[i]; }) &&
                std::any_of(choice.rows[ri + 1].begin(), choice.rows[ri + 1].end(),
                            [&](auto i) { return bucks[i]; }))
                gap = 8;
            y = bottom + gap;
        }
        return out;
    };
    double foreign_bound = 5;
    for (const auto &s : structures)
        if (text(s, "type") == "fb_cluster") {
            foreign_bound = number(s, "min_to_foreign_sw_mm", 5);
            break;
        }
    auto okay = [&](const Parts &ps) {
        for (const auto &s : structures)
            if (text(s, "type") == "fb_cluster" && object_field(s, "foreign_ic")) {
                auto ic = find(ps, bref(text(s, "foreign_ic")));
                if (!ic)
                    continue;
                auto ip = pads(*ic);
                auto ind = find(ps, bref(text(s, "foreign_inductor")));
                auto lp = ind ? pads(*ind) : NamedBoxes{};
                for (const auto &lib : strings(s, "members")) {
                    auto m = find(ps, bref(lib));
                    if (!m)
                        continue;
                    auto mp = pads(*m);
                    if (distance(ip, mp, {text(s, "foreign_sw_pin")}) < foreign_bound ||
                        distance(lp, mp) < foreign_bound)
                        return false;
                }
            }
        return true;
    };
    std::vector<Parts> candidates_layout;
    std::vector<std::tuple<double, std::size_t, std::size_t>> scored;
    std::vector<std::size_t> valid;
    for (std::size_t i = 0; i < choices.size(); ++i) {
        auto ps = lay(choices[i]);
        auto w = row_extent(ps).first;
        bool ok = okay(ps);
        if (ok)
            valid.push_back(i);
        if (w <= 46 && ok)
            scored.emplace_back(py_round(w, 4), choices[i].rows.size(), i);
        candidates_layout.push_back(std::move(ps));
    }
    std::size_t chosen = 0;
    if (!scored.empty()) {
        std::sort(scored.begin(), scored.end());
        chosen = std::get<2>(scored.front());
    } else {
        if (valid.empty())
            for (std::size_t i = 0; i < choices.size(); ++i)
                valid.push_back(i);
        chosen = *std::min_element(valid.begin(), valid.end(), [&](auto a, auto b) {
            return row_extent(candidates_layout[a]).first < row_extent(candidates_layout[b]).first;
        });
    }
    auto placed = face(candidates_layout[chosen], output_refs(), false);
    PcbStageResult result;
    std::tie(result.w, result.h) = row_extent(placed);
    double bottom = extent(placed).y1;
    for (const auto &p : placed) {
        result.top[p.ref] = {p.x, p.y};
        if (std::abs(p.rot) > 1e-6 && !connector(*p.mod))
            result.rotations[p.ref] = normalize(p.rot);
    }
    std::vector<std::string> leftovers;
    for (const auto &r : in.refs)
        if (!find(placed, r))
            leftovers.push_back(r);
    if (!leftovers.empty()) {
        auto bands = leftover(leftovers, std::max(result.w - 2 * zone_pad, 8.));
        double dy = bottom + 2 - zone_pad;
        for (const auto &[r, x, y] : bands.first.placed)
            result.top[r] = {py_round(x, 4), py_round(y + dy, 4)};
        for (const auto &[r, x, y] : bands.second.placed)
            result.bottom[r] = {py_round(x, 4), py_round(y + dy, 4)};
        result.w = py_round(std::max({result.w, bands.first.packed_w, bands.second.packed_w}), 4);
        result.h = py_round(
            std::max({result.h, dy + bands.first.packed_h, dy + bands.second.packed_h}), 4);
    }
    return result;
}
} // namespace schgen::pcb_stage
