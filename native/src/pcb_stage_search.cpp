#include "pcb_stage_internal.hpp"

namespace schgen::pcb_stage {
Parts Engine::candidates(const std::string &ref, const std::vector<Attract> &att,
                         const std::vector<Repel> &rep, const Parts &placed, double pad,
                         const std::vector<Box4> &forbid) {
    if (att.empty())
        throw PcbZoneInfeasible("contract member has no attractor: " + ref);
    auto subject = part(ref);
    std::vector<BoundGroup> attracts, repels;
    Box4 target;
    double bound = std::numeric_limits<double>::infinity();
    for (const auto &a : att) {
        auto p = find(placed, a.ref);
        if (!p)
            throw PcbZoneInfeasible("unplaced attractor: " + a.ref);
        auto pb = pads(*p);
        BoundGroup group;
        for (const auto &[name, b] : pb)
            if (a.pins.empty() || std::find(a.pins.begin(), a.pins.end(), name) != a.pins.end())
                group.boxes.push_back(b);
        group.limit = tight_bound(a.bound);
        attracts.push_back(group);
        if (a.bound < bound) {
            bound = a.bound;
            target = pinbox(pb, a.pins);
        }
    }
    for (const auto &r : rep) {
        auto p = find(placed, r.ref);
        if (!p)
            throw PcbZoneInfeasible("unplaced repulsor: " + r.ref);
        BoundGroup group;
        for (const auto &[name, b] : pads(*p))
            if (r.pin.empty() || name == r.pin)
                group.boxes.push_back(b);
        group.limit = tight_pad(r.minimum);
        repels.push_back(group);
    }
    auto member_pins = static_cast<int>(pads(subject.mod).size());
    double own_need = member_pins >= 3 ? need(member_pins) : 0;
    std::vector<Subject> subjects;
    for (const auto &p : placed) {
        auto np = static_cast<int>(pads(p.mod).size());
        if (np >= 3 && !passive(ref, member_pins))
            subjects.push_back({body(p), credit(need(np))});
        if (own_need && !passive(p.ref, np))
            subjects.push_back({body(p), credit(own_need)});
    }
    std::map<std::string, std::string> mem_nets;
    std::map<std::string, std::vector<FloorplanPoint>> net_pts;
    if (!in.pad_nets.empty() && member_pins >= 4) {
        std::set<std::string> wanted;
        for (const auto &[pn, b] : pads(subject.mod)) {
            (void)b;
            auto i = in.pad_nets.find({ref, pn});
            if (i != in.pad_nets.end()) {
                mem_nets[pn] = i->second;
                wanted.insert(i->second);
            }
        }
        for (const auto &p : placed)
            for (const auto &[pn, b] : pads(p)) {
                auto i = in.pad_nets.find({p.ref, pn});
                if (i != in.pad_nets.end() && wanted.count(i->second))
                    net_pts[i->second].push_back(rect_center(b));
            }
    }
    auto sig = [&](double rot) {
        std::vector<std::tuple<std::string, double, double, double, double>> rows;
        for (const auto &[pn, b] : pads(subject.mod, rot)) {
            auto i = mem_nets.find(pn);
            if (i != mem_nets.end())
                rows.emplace_back(i->second, b.x0, b.y0, b.x1, b.y1);
        }
        return named_box_center_sigs(rows, 2);
    };
    std::vector<double> rotations{90, 0};
    if (!net_pts.empty() && sig(0) != sig(180))
        rotations = {0, 90, 180, 270};
    std::vector<std::vector<AlignTerm>> aligns;
    std::vector<std::vector<Box4>> relative;
    std::vector<Box4> bodies_rot;
    for (double rot : rotations) {
        std::vector<AlignTerm> terms;
        for (const auto &[pn, b] : pads(subject.mod, rot)) {
            auto m = mem_nets.find(pn);
            if (m == mem_nets.end())
                continue;
            auto n = net_pts.find(m->second);
            if (n == net_pts.end())
                continue;
            auto c = rect_center(b);
            terms.push_back({c.first, c.second, n->second});
        }
        aligns.push_back(terms);
        relative.push_back(values(pads(subject.mod, rot)));
        subject.rot = rot;
        bodies_rot.push_back(body(subject));
    }
    auto center = rect_center(target);
    int n = std::min(
        static_cast<int>(
            (std::max(target.x1 - target.x0, target.y1 - target.y0) / 2 + bound + 9 + pad) / .5),
        60);
    auto result =
        seat_scan(center.first, center.second, n, .5, clear + pad, .1, 400, bodies(placed), forbid,
                  subjects, attracts, repels, rotations, relative, bodies_rot, aligns);
    if (result.truncated)
        events.push_back("cand_cap_truncated");
    Parts out;
    for (const auto &h : result.hits)
        out.push_back(part(ref, h.rot, h.cx, h.cy));
    return out;
}
Parts Engine::seat_all(const std::vector<Demand> &demands, const NamedBoxes &ib, Box4 icb,
                       const Parts &skeleton, double pad, bool forbid_right) {
    std::map<std::string, CandList> candidates;
    std::vector<std::string> order;
    for (const auto &d : demands) {
        auto p = part(d.ref);
        auto target = pinbox(ib, d.pins);
        auto c = rect_center(target);
        std::vector<Box4> target_boxes, keep_boxes;
        for (const auto &[name, b] : ib) {
            if (d.pins.empty() || std::find(d.pins.begin(), d.pins.end(), name) != d.pins.end())
                target_boxes.push_back(b);
            if (std::find(d.keep.begin(), d.keep.end(), name) != d.keep.end())
                keep_boxes.push_back(b);
        }
        std::vector<Box4> b;
        std::vector<std::vector<Box4>> rel;
        for (double rot : {90., 0.}) {
            p.rot = rot;
            b.push_back(body(p));
            rel.push_back(values(pads(p.mod, rot)));
        }
        auto got =
            seat_candidates(c.first, c.second, static_cast<int>((9 + pad) / .5), .5, clear + pad,
                            tight_bound(d.bound), d.minimum, forbid_right, 400, icb,
                            bodies(skeleton), {90, 0}, b, rel, target_boxes, keep_boxes);
        if (got.truncated)
            events.push_back("cand_cap_truncated");
        candidates[d.ref] = std::move(got);
        order.push_back(d.ref);
    }
    std::stable_sort(order.begin(), order.end(), [&](const auto &a, const auto &b) {
        return candidates.at(a).hits.size() < candidates.at(b).hits.size();
    });
    std::vector<std::vector<Box4>> rows;
    for (const auto &r : order) {
        std::vector<Box4> boxes;
        for (const auto &h : candidates.at(r).hits)
            boxes.push_back(h.body);
        rows.push_back(std::move(boxes));
    }
    auto dfs = seat_dfs(rows, bodies(skeleton), clear + pad, 300000);
    if (dfs.budget_hit)
        events.push_back("seat_node_budget");
    std::map<std::string, int> selected;
    if (dfs.solved)
        for (std::size_t i = 0; i < order.size(); ++i)
            selected[order[i]] = dfs.pick[i];
    Parts out;
    for (const auto &d : demands) {
        const auto &hits = candidates.at(d.ref).hits;
        if (hits.empty())
            out.push_back(part(d.ref, 90, icb.x0 - 1, 0));
        else {
            const auto &h = hits.at(static_cast<std::size_t>(selected[d.ref]));
            out.push_back(part(d.ref, h.rot, h.cx, h.cy));
        }
    }
    return out;
}
double Engine::flip_rotation(const std::string &ref) {
    const auto p = part(ref);
    if (pads(p.mod).size() < 10 || connector(*p.mod) || in.sheet.rfind("som_j", 0) == 0)
        return 0;
    std::vector<FloorplanPoint> centers;
    for (const auto &[name, type, x, y, r, w, h] : p.mod->pads) {
        (void)type;
        (void)r;
        (void)w;
        (void)h;
        if (!name.empty())
            centers.emplace_back(x, y);
    }
    if (!pad_set_180_symmetric(centers, .1))
        return 0;
    std::string lib;
    for (const auto &[l, b] : in.board_refs)
        if (b == ref) {
            lib = l;
            break;
        }
    auto ni = in.inter_nets.find(lib);
    if (ni == in.inter_nets.end() || ni->second.empty() || in.partners.empty())
        return 0;
    const PcbStagePartner *partner = nullptr;
    std::size_t best = 0;
    for (const auto &[sheet, v] : in.partners) {
        (void)sheet;
        std::size_t cnt = 0;
        for (const auto &[net, pins] : ni->second) {
            (void)pins;
            if (v.nets.count(net))
                ++cnt;
        }
        if (!partner || cnt > best) {
            partner = &v;
            best = cnt;
        }
    }
    if (best * 100 < 60 * ni->second.size())
        return 0;
    auto coords = [&](const PcbCheckFootprintPtr &fp, double rot) {
        std::vector<std::tuple<std::string, double, double>> c;
        for (const auto &[name, b] : pads(fp, rot)) {
            auto center = rect_center(b);
            c.emplace_back(name, center.first, center.second);
        }
        auto v = long_axis_coords(c);
        return std::map<std::string, double>(v.begin(), v.end());
    };
    auto j = coords(partner->footprint, partner->rotation);
    auto inv = [&](double rot) {
        auto own = coords(p.mod, rot);
        std::vector<std::tuple<double, double, std::string>> pairs;
        for (const auto &[net, pins] : ni->second) {
            auto q = partner->nets.find(net);
            if (q == partner->nets.end())
                continue;
            std::vector<double> a, b;
            for (const auto &pin : pins)
                if (own.count(pin))
                    a.push_back(own.at(pin));
            for (const auto &pin : q->second)
                if (j.count(pin))
                    b.push_back(j.at(pin));
            if (!a.empty() && !b.empty())
                pairs.emplace_back(std::accumulate(a.begin(), a.end(), 0.) / a.size(),
                                   std::accumulate(b.begin(), b.end(), 0.) / b.size(), net);
        }
        return inversion_count(pairs);
    };
    return inv(180) < inv(0) ? 180 : 0;
}
Parts Engine::proximity_cluster(const std::string &anchor) {
    std::vector<Demand> demands;
    for (const auto &s : optional(in.contract, "structures").array_value)
        if (text(s, "type") == "proximity" && bref(text(s, "anchor")) == anchor) {
            std::vector<std::string> keep;
            double minimum = 0;
            for (const auto &mf : optional(s, "min_from").array_value)
                if (bref(text(mf, "part")) == anchor && !text(mf, "pin").empty()) {
                    keep = {text(mf, "pin")};
                    minimum = number(mf, "min_mm");
                    break;
                }
            for (const auto &lib : strings(s, "members")) {
                auto b = bref(lib);
                if (b.empty())
                    throw PcbZoneInfeasible("proximity cluster: unresolvable member " + lib);
                demands.push_back(
                    {b, strings(s, "anchor_pins"), number(s, "max_mm"), keep, minimum});
            }
        }
    auto a = part(anchor);
    if (demands.empty())
        return {a};
    const auto ib = pads(a);
    auto icb = body(a);
    for (int scale = 0; scale < 20; ++scale) {
        auto seated = seat_all(demands, ib, icb, {a}, scale * .25, false);
        Parts all{a};
        all.insert(all.end(), seated.begin(), seated.end());
        if (overlap(all))
            continue;
        bool okay = true;
        for (const auto &d : demands) {
            auto p = find(seated, d.ref);
            if (!p) {
                okay = false;
                continue;
            }
            auto pb = pads(*p);
            if (distance(ib, pb, d.pins) > tight_bound(d.bound) ||
                (!d.keep.empty() && distance(ib, pb, d.keep) < d.minimum))
                okay = false;
        }
        if (okay)
            return all;
    }
    throw PcbZoneInfeasible(
        "proximity cluster at " + anchor +
        ": 20-scale widen exhausted without a collision-free, bound-satisfying seat");
}
Parts Engine::solve_contract() {
    std::map<std::string, std::vector<Attract>> att;
    std::map<std::string, std::vector<Repel>> rep;
    std::set<std::string> all, members;
    for (const auto &s : optional(in.contract, "structures").array_value)
        if (text(s, "type") == "proximity") {
            auto a = bref(text(s, "anchor"));
            if (a.empty())
                throw PcbZoneInfeasible("contract graph: proximity anchor does not resolve: " +
                                        text(s, "anchor"));
            all.insert(a);
            for (const auto &lib : strings(s, "members")) {
                auto b = bref(lib);
                if (b.empty())
                    throw PcbZoneInfeasible("contract graph: proximity member does not resolve: " +
                                            lib);
                all.insert(b);
                members.insert(b);
                att[b].push_back({a, strings(s, "anchor_pins"), number(s, "max_mm")});
                for (const auto &mf : optional(s, "min_from").array_value) {
                    auto r = bref(text(mf, "part"));
                    if (r.empty())
                        continue;
                    rep[b].push_back({r, text(mf, "pin"), number(mf, "min_mm")});
                    all.insert(r);
                }
            }
        }
    if (members.empty())
        throw PcbZoneInfeasible("contract graph: no resolvable proximity members");
    std::map<std::string, std::set<std::string>> adj, deps;
    for (const auto &m : members) {
        for (const auto &a : att[m]) {
            adj[m].insert(a.ref);
            adj[a.ref].insert(m);
            deps[m].insert(a.ref);
        }
        for (const auto &r : rep[m]) {
            adj[m].insert(r.ref);
            adj[r.ref].insert(m);
            deps[m].insert(r.ref);
        }
        deps[m].erase(m);
    }
    std::set<std::string> roots, conn_roots, seen;
    FloorplanRotations rotations;
    for (const auto &r : all)
        if (!members.count(r)) {
            roots.insert(r);
            if (connector(*in.footprints.at(r))) {
                conn_roots.insert(r);
                if (!in.outer_dir.empty())
                    rotations[r] = connector_rotation(*in.footprints.at(r), in.outer_dir, quantization);
            } else
                rotations[r] = flip_rotation(r);
        }
    auto ov = direction(in.outer_dir);
    bool along_y = ov && std::abs(ov->first) > std::abs(ov->second);
    std::vector<Parts> clusters;
    for (const auto &seed : all) {
        if (seen.count(seed))
            continue;
        std::set<std::string> comp;
        std::vector<std::string> stack{seed};
        while (!stack.empty()) {
            auto q = stack.back();
            stack.pop_back();
            if (!seen.insert(q).second)
                continue;
            comp.insert(q);
            for (const auto &x : adj[q])
                if (!seen.count(x))
                    stack.push_back(x);
        }
        std::vector<std::pair<std::string, std::vector<std::string>>> dep_rows;
        for (const auto &r : comp)
            dep_rows.push_back({r, {deps[r].begin(), deps[r].end()}});
        auto order = topo_order({comp.begin(), comp.end()}, dep_rows);
        if (!order)
            throw PcbZoneInfeasible("contract graph: cyclic constraint graph over component " +
                                    seed);
        bool solved = false;
        for (int scale = 0; scale < 24; ++scale) {
            double pad = scale * .25, cursor = 0;
            bool prev_conn = false;
            Parts placed;
            for (const auto &r : comp)
                if (roots.count(r)) {
                    bool is_conn = conn_roots.count(r);
                    double gap = prev_conn && is_conn ? 20 : 2;
                    auto p = part(r, rotations[r]);
                    auto b = body(p);
                    if (along_y)
                        p.y = py_round(cursor - b.y0, 4);
                    else
                        p.x = py_round(cursor - b.x0, 4);
                    b = body(p);
                    cursor = (along_y ? b.y1 : b.x1) + clear + pad + gap;
                    placed.push_back(p);
                    prev_conn = is_conn;
                }
            std::vector<Box4> forbid;
            if (ov) {
                std::vector<double> faces;
                auto [vx, vy] = *ov;
                for (const auto &p : placed)
                    if (conn_roots.count(p.ref)) {
                        auto b = pinbox(pads(p), {});
                        faces.push_back(vx > 0 ? b.x1 : vx < 0 ? b.x0 : vy > 0 ? b.y1 : b.y0);
                    }
                if (!faces.empty()) {
                    double face =
                        vx > 0 || vy > 0
                            ? *std::min_element(faces.begin(), faces.end()) - seat_slide()
                            : *std::max_element(faces.begin(), faces.end()) + seat_slide();
                    forbid.push_back(vx > 0   ? Box4{face, -1e4, 1e4, 1e4}
                                     : vx < 0 ? Box4{-1e4, -1e4, face, 1e4}
                                     : vy > 0 ? Box4{-1e4, face, 1e4, 1e4}
                                              : Box4{-1e4, -1e4, 1e4, face});
                }
            }
            bool feasible = true;
            for (const auto &r : *order)
                if (!roots.count(r)) {
                    auto c = candidates(r, att[r], rep[r], placed, pad, forbid);
                    if (c.empty()) {
                        feasible = false;
                        break;
                    }
                    placed.push_back(c.front());
                }
            if (!feasible)
                continue;
            Parts sorted;
            for (const auto &r : *order)
                sorted.push_back(*find(placed, r));
            if (!overlap(sorted)) {
                clusters.push_back(std::move(sorted));
                solved = true;
                break;
            }
        }
        if (!solved)
            throw PcbZoneInfeasible("contract graph: component " + seed +
                                    " found no collision-free seat after the 24-scale widen");
    }
    return compose(clusters, conn_roots);
}
Parts Engine::compose(const std::vector<Parts> &clusters, const std::set<std::string> &conns) {
    auto ov = direction(in.outer_dir);
    double vx = ov ? ov->first : 0, vy = ov ? ov->second : 0;
    bool along_y = ov && std::abs(vx) > std::abs(vy);
    double cursor = 0;
    bool prev = false;
    std::vector<Parts> frames;
    for (const auto &cl : clusters) {
        bool has =
            std::any_of(cl.begin(), cl.end(), [&](const auto &p) { return conns.count(p.ref); });
        double gap = prev && has ? 20 : 2;
        auto b = extent(cl);
        frames.push_back(
            shifted(cl, -b.x0 + (along_y ? 0 : cursor), -b.y0 + (along_y ? cursor : 0)));
        cursor += (along_y ? b.y1 - b.y0 : b.x1 - b.x0) + clear + gap;
        prev = has;
    }
    auto face = [&](const Parts &cl) -> std::optional<double> {
        std::vector<double> fs;
        for (const auto &p : cl)
            if (conns.count(p.ref)) {
                auto b = pinbox(pads(p), {});
                fs.push_back(vx > 0 ? b.x1 : vx < 0 ? b.x0 : vy > 0 ? b.y1 : b.y0);
            }
        if (fs.empty())
            return {};
        return vx > 0 || vy > 0 ? *std::max_element(fs.begin(), fs.end())
                                : *std::min_element(fs.begin(), fs.end());
    };
    if (ov && !conns.empty()) {
        std::vector<double> fs;
        for (const auto &cl : frames) {
            auto f = face(cl);
            if (f)
                fs.push_back(*f);
        }
        if (!fs.empty()) {
            double target = vx > 0 || vy > 0 ? *std::max_element(fs.begin(), fs.end())
                                             : *std::min_element(fs.begin(), fs.end());
            for (auto &cl : frames) {
                auto f = face(cl);
                if (f) {
                    double d = py_round(target - *f, 4);
                    if (d)
                        cl = shifted(cl, vx ? d : 0, vy ? d : 0);
                }
            }
            double line = py_round(target + (vx < 0 || vy < 0 ? seat_slide() : -seat_slide()), 4);
            for (auto &cl : frames)
                if (!face(cl)) {
                    auto b = extent(cl);
                    double edge = vx > 0 ? b.x1 : vx < 0 ? b.x0 : vy > 0 ? b.y1 : b.y0;
                    double d = vx > 0 || vy > 0 ? std::min(0., py_round(line - edge, 4))
                                                : std::max(0., py_round(line - edge, 4));
                    if (d)
                        cl = shifted(cl, vx ? d : 0, vy ? d : 0);
                }
        }
    }
    Parts out;
    for (const auto &cl : frames)
        out.insert(out.end(), cl.begin(), cl.end());
    return out;
}
} // namespace schgen::pcb_stage
