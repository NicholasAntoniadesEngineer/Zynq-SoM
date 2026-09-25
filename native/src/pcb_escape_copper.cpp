#include "pcb_escape_internal.hpp"
#include <numeric>

namespace schgen {
namespace {
using namespace pcb_escape;
using CopperObstacle = std::tuple<double, double, double, double, double, std::string>;
using Hole = std::tuple<double, double, double, std::string>;
struct Obstacles {
    std::vector<CopperObstacle> front, back, same;
    std::vector<Hole> holes;
};
struct Via : SeatVia {
    std::string role = "stitch";
};
struct Member {
    std::string pad, net, klass;
    double u, v;
    int rank;
};
struct Job {
    int rank;
    std::string ref;
    double first;
    std::vector<Member> members;
};
using Through = std::vector<std::vector<std::string>>;
Through through_pads(const PcbCheckModel &m) {
    Through out(m.insts.size());
    for (std::size_t i = 0; i < m.insts.size(); ++i)
        if (m.insts[i].mod)
            for (const auto &p : m.insts[i].mod->pads)
                if (std::get<1>(p) == "thru_hole" || std::get<1>(p) == "np_thru_hole")
                    out[i].push_back(std::get<0>(p));
    return out;
}
std::vector<std::size_t> sorted_instances(const PcbCheckModel &m) {
    std::vector<std::size_t> v(m.insts.size());
    std::iota(v.begin(), v.end(), 0);
    std::stable_sort(v.begin(), v.end(),
                     [&](auto a, auto b) { return m.insts[a].ref < m.insts[b].ref; });
    return v;
}
Obstacles collect_obstacles(const PcbEscapeInput &input, const PcbCheckInstance &inst, Box4 region,
                            const std::vector<std::size_t> &sorted, const Through &through) {
    Obstacles obs;
    const auto &m = input.model();
    for (auto i : sorted) {
        const auto &oi = m.insts[i];
        const auto &boxes = input.geometry().geometry_at(i).pad_boxes;
        std::set<std::string> thru(through[i].begin(), through[i].end());
        for (const auto &[pad, bb] : boxes) {
            const auto net = net_name(oi, pad), label = oi.ref + "(" + oi.sheet + ")." + pad;
            auto cls = m.netclass_of.find(net);
            double rule = net_clearance_rule(cls != m.netclass_of.end() && cls->second == "POWER");
            auto b = board_box_to_uv(inst.x, inst.y, inst.rotation, bb);
            int bucket =
                obstacle_bucket(region.x0, region.y0, region.x1, region.y1, b.x0, b.y0, b.x1, b.y1,
                                oi.ref == inst.ref, net == "GND", oi.side == "top");
            if (!bucket)
                continue;
            (bucket == 1   ? obs.same
             : bucket == 2 ? obs.front
                           : obs.back)
                .emplace_back(b.x0, b.y0, b.x1, b.y1, rule, label);
            if (thru.count(pad)) {
                auto [u, v, r] = obstacle_hole(b.x0, b.y0, b.x1, b.y1);
                obs.holes.emplace_back(u, v, r, label);
            }
        }
    }
    return obs;
}
std::vector<std::tuple<double, double, std::string>> ground_pads(const PcbCheckInstance &inst,
                                                                 const Connector &c) {
    std::vector<std::tuple<double, double, std::string>> out;
    for (const auto &[pad, n] : inst.pad_nets)
        if (n.first > 0 && n.second == "GND") {
            auto p = c.pads.find(pad);
            if (p != c.pads.end())
                out.emplace_back(py_round(p->second.first, 4), py_round(p->second.second, 4), pad);
        }
    std::sort(out.begin(), out.end());
    return out;
}
void self_check(const PcbCheckModel &m, const std::map<std::string, Connector> &conns,
                const std::map<std::string, std::vector<Via>> &by_conn,
                const std::map<std::string, std::vector<EscapeLadderSeg>> &ladders, Box4 zone) {
    for (const auto &[ref, vias] : by_conn) {
        const auto &c = conns.at(ref);
        const auto &inst = m.insts[c.index];
        std::vector<std::tuple<double, double, double>> vr;
        for (const auto &v : vias)
            vr.emplace_back(v.u, v.v, v.dia);
        std::vector<std::tuple<double, double, double, double, double, std::string>> sr;
        for (const auto &s : ladders.at(ref))
            sr.emplace_back(s.ax, s.ay, s.bx, s.by, s.w, s.role);
        std::vector<std::pair<double, double>> pr;
        for (const auto &[u, v, pad] : ground_pads(inst, c)) {
            (void)pad;
            pr.emplace_back(u, v);
        }
        auto check = escape_ladder_connected(vr, sr, pr, c.contacts.half_w, c.contacts.half_h);
        if (check.via_seg_components != 1)
            throw PcbEscapeError(ref + ": LAW-0 self-check FAILED — ladder+vias form " +
                                 std::to_string(check.via_seg_components) +
                                 " components, expected 1");
        for (const auto &v : vias) {
            auto [x, y] = board(inst, v.u, v.v);
            if (!via_in_escape_region(x, y, zone, .5))
                throw PcbEscapeError(ref + ": via at (" + f(x, 2) + "," + f(y, 2) +
                                     ") outside the escape region " + box_repr(zone) +
                                     " (+0.5 margin)");
        }
        if (check.pad_stubs < 2)
            throw PcbEscapeError(ref + ": only " + std::to_string(check.pad_stubs) +
                                 " GND-pad stub(s) — rule is >= 2 per remediated connector");
    }
}
std::vector<PcbEscapeCoexistence> coexistence(const PcbEscapeInput &input,
                                              const std::map<std::string, Connector> &conns,
                                              const std::vector<SeatLedger> &ledger,
                                              const std::vector<std::size_t> &sorted) {
    std::vector<PcbEscapeCoexistence> out;
    std::set<std::string> escal;
    for (const auto &e : ledger)
        if (e.kind == "split_u" || e.kind == "split_row")
            escal.insert(e.conn);
    const std::map<std::string, std::string> bases = {
        {"som_decoupling",
         "SoM rail bypass — function requires under-SoM adjacency (ADD-don't-relocate)"},
        {"hdmi_rx_term", "TMDS termination must live at the connector; its pads narrow the channel "
                         "windows (seat ledger names the splits) — evict only if a failing contact "
                         "becomes unconstructable; consumer: bottom-channel-keepout unit"},
        {"power_som",
         "SoM rail-entry parts; outside all live windows this build (re-derived every build)"}};
    for (const auto &[ref, c] : conns) {
        const auto &inst = input.model().insts[c.index];
        const auto &g = c.contacts;
        const auto region = coexistence_region(g.span_u, g.row_v, g.half_h, lane_handle, .50);
        for (auto i : sorted) {
            const auto &oi = input.model().insts[i];
            if (oi.side != "bottom" || oi.ref == inst.ref)
                continue;
            const auto &boxes = input.geometry().geometry_at(i).pad_boxes;
            if (!std::any_of(boxes.begin(), boxes.end(), [&](const auto &b) {
                    return coexistence_box_hit(inst.x, inst.y, inst.rotation, b.second,
                                               region.first, region.second);
                }))
                continue;
            auto b = bases.find(oi.sheet);
            std::string verdict = "STAY", basis;
            if (b != bases.end()) {
                basis = b->second;
                if (oi.sheet == "hdmi_rx_term" && escal.count(ref))
                    verdict = "CONSTRAINT";
            } else
                basis = "foreign L4 stray inside the escape region but outside every live via "
                        "window this build — re-derived every build; becomes EVICT (consumer: "
                        "bottom-channel-keepout unit) only on a proven window closure";
            out.push_back({ref, oi.ref, oi.sheet, verdict, basis});
        }
    }
    return out;
}
} // namespace

PcbEscapeCopperResult build_pcb_escape_copper(const PcbEscapeInput &input) {
    using namespace pcb_escape;
    const auto &m = input.model();
    auto gn = m.net_numbers.find("GND");
    if (gn == m.net_numbers.end() || !gn->second)
        throw PcbEscapeError(
            "net 'GND' absent from the model net table — refusing to emit net-0 copper (LAW 0)");
    const auto conn_indices = connectors(m);
    std::vector<std::string> names;
    for (const auto &[ref, i] : conn_indices) {
        (void)i;
        names.push_back(ref);
    }
    if (names != std::vector<std::string>{"J1", "J2", "J3"})
        throw PcbEscapeError("expected the 3 DF40 receptacles (som_j1/2/3), found " +
                             list_repr(names));
    PcbEscapeCopperResult out;
    auto &meta = out.meta;
    meta.v1 = input.return_path();
    std::map<std::string, std::vector<ReturnPathViolation>> failing;
    for (const auto &v : meta.v1.violations)
        failing[v.ref].push_back(v);
    if (!input.keepout())
        throw PcbEscapeError("model has no SoM keepout — escape region underivable");
    const auto zone = grow_rect(*input.keepout(), 2.);
    // Source escape uses ORIGIN_X/Y, not a caller's metadata override.
    meta.plane = canonical_plane_rect(25., 25., m.board_w, m.board_h, .5);
    if (!rect_covers(meta.plane, zone))
        throw PcbEscapeError("the canonical In1 GND plane " + box_repr(meta.plane) +
                             " does not cover the escape region " + box_repr(zone) +
                             " — the return stitching has no plane to land on (GAP1 geometry "
                             "changed; re-derive deliberately)");
    for (std::size_t i = 0; i < m.insts.size(); ++i) {
        const auto &oi = m.insts[i];
        if (!starts(oi.value, "HX5008") && !starts(oi.value, "KH-5224"))
            continue;
        auto vr = isolation_void_rect(input.geometry().courtyard_at(i), .6);
        auto label = "ethernet_isolation_void_" + oi.ref;
        meta.voids_checked.push_back(label);
        if (rects_intersect_open(vr, zone))
            throw PcbEscapeError(
                "In1 plane VOID " + label + " " + box_repr(vr) + " intersects the escape region " +
                box_repr(zone) +
                " — the return plane under the DF40 field would be perforated (a placement wave "
                "moved the ethernet media parts under the SoM?); fail loud");
    }
    auto sorted = sorted_instances(m);
    auto through = through_pads(m);
    std::vector<std::string> barrels;
    for (auto i : sorted) {
        const auto &oi = m.insts[i];
        if (through[i].empty())
            continue;
        const auto &boxes = input.geometry().geometry_at(i).pad_boxes;
        for (const auto &pad : through[i]) {
            auto net = net_name(oi, pad);
            if (net == "GND")
                continue;
            auto it = boxes.find(pad);
            if (it == boxes.end())
                continue;
            auto [x, y] = rect_center(it->second);
            if (point_in_rect(x, y, zone))
                barrels.push_back(oi.ref + "." + pad + " (" + (net.empty() ? "no-net" : net) +
                                  ") at (" + f(x, 2) + "," + f(y, 2) + ")");
        }
    }
    if (!barrels.empty())
        throw PcbEscapeError(
            "foreign thru/NPTH barrel(s) inside the ESCAPE REGION " + box_repr(zone) + ": " +
            list_repr(barrels) +
            " — the documented future path is an octagonal carve-out (r = hole/2 + 0.2 + 0.1); it "
            "is NOT implemented because the precondition holds on every measured build; fail loud "
            "instead of silently emitting an unproven fill");
    const auto conns = prepare_connectors(m);
    std::map<std::string, Obstacles> obstacles;
    std::map<std::string, std::vector<Via>> by_conn;
    std::vector<Job> jobs;
    for (const auto &[ref, violations] : failing) {
        auto ci = conns.find(ref);
        if (ci == conns.end())
            throw PcbEscapeError("return-path connector missing from placed model: " + ref);
        const auto &c = ci->second;
        std::map<std::string, Member> by_pad;
        std::vector<std::pair<double, std::string>> pts;
        std::vector<double> us;
        for (const auto &v : violations) {
            auto pos = c.pads.find(v.pad);
            if (pos == c.pads.end())
                throw PcbEscapeError(ref + ": return-path pad missing from footprint: " + v.pad);
            auto [u, w] = pos->second;
            const auto &cl = input.classify(v.net);
            by_pad[v.pad] = {v.pad, v.net, cl.klass, u, w, cl.rank()};
            pts.emplace_back(u, v.pad);
            us.push_back(u);
            meta.triage[ref + "." + v.pad] = cl;
        }
        auto region = obstacle_scan_region(rounded_unique_sorted(us, 3), 6.);
        obstacles.emplace(ref, collect_obstacles(input, m.insts[c.index], region, sorted, through));
        for (const auto &band : band_cover(pts, construct_reach(radius, c.contacts.row_v))) {
            Job j{2, ref, band.front().first, {}};
            for (const auto &[u, pad] : band) {
                (void)u;
                j.members.push_back(by_pad.at(pad));
                j.rank = std::min(j.rank, by_pad.at(pad).rank);
            }
            jobs.push_back(std::move(j));
        }
    }
    std::stable_sort(jobs.begin(), jobs.end(), [](const auto &a, const auto &b) {
        return std::tie(a.rank, a.ref, a.first) < std::tie(b.rank, b.ref, b.first);
    });
    for (const auto &job : jobs) {
        const auto &ref = job.ref;
        auto &obs = obstacles.at(ref);
        const auto &g = conns.at(ref).contacts;
        std::vector<std::tuple<std::string, double, double>> members;
        std::vector<std::string> pads, nets;
        for (const auto &v : job.members) {
            members.emplace_back(v.pad, v.u, v.v);
            pads.push_back(v.pad);
            nets.push_back(v.net);
        }
        auto result = seat_band(members, obs.front, obs.back, obs.same, obs.holes, g.row_v,
                                g.half_h, ladder(), clear(), .15, radius, lattice, ref, 0);
        meta.ledger.insert(meta.ledger.end(), result.ledger.begin(), result.ledger.end());
        if (result.vias.empty()) {
            auto audit = result.audit;
            if (audit.size() > 40)
                audit.erase(audit.begin(), audit.end() - 40);
            throw PcbEscapeError(
                ref + ": no feasible stitch-via seat for contacts " + list_repr(pads) + " (nets " +
                list_repr(nets) +
                ") at R_CONSTRUCT=1.8; candidate audit (last 40): " + list_repr(audit) +
                " — remedy is the queued bottom-channel-keepout unit (move the blocking B.Cu "
                "strays in a reviewed byte-diff wave), never a threshold relax");
        }
        std::vector<std::pair<double, double>> sites;
        for (const auto &seat : result.vias) {
            Via v;
            static_cast<SeatVia &>(v) = seat;
            by_conn[ref].push_back(v);
            sites.emplace_back(v.u, v.v);
            obs.holes.emplace_back(v.u, v.v, v.drill / 2, "escape-via " + ref);
        }
        for (const auto &v : job.members)
            meta.coverage_mm[ref][v.pad] = min_hypot_to_points(v.u, v.v, sites);
    }
    for (auto &[ref, vias] : by_conn) {
        if (vias.size() >= 2)
            continue;
        const auto base = vias.front();
        auto &obs = obstacles.at(ref);
        auto u = escape_redundancy_u(base.u, base.v, base.dia, base.drill, obs.front, obs.back,
                                     obs.same, obs.holes, clear(), 1., lattice, 21);
        if (!u)
            throw PcbEscapeError(
                ref +
                ": no feasible redundancy-partner seat (judgment:2 — a lone stitch via is a SPOF)");
        Via v;
        v.u = *u;
        v.v = base.v;
        v.dia = base.dia;
        v.drill = base.drill;
        v.role = "redundant";
        vias.push_back(v);
        obs.holes.emplace_back(v.u, v.v, v.drill / 2, "escape-via " + ref);
        SeatLedger l;
        l.kind = "redundant_via";
        l.conn = ref;
        l.u = v.u;
        l.v = v.v;
        meta.ledger.push_back(l);
    }
    std::map<std::string, std::vector<EscapeLadderSeg>> ladders;
    for (const auto &[ref, vias] : by_conn) {
        const auto &c = conns.at(ref);
        const auto &inst = m.insts[c.index];
        std::vector<std::pair<double, double>> uv;
        for (const auto &v : vias)
            uv.emplace_back(v.u, v.v);
        std::vector<EscapeLadderSeg> segs;
        const auto grounds = ground_pads(inst, c);
        if (grounds.empty())
            throw PcbEscapeError(ref + ": no GND attach options on the connector");
        try {
            segs = escape_ladder_plan(grounds, uv, c.contacts.pitch, .001, c.contacts.row_v, .30,
                                      .25, .30);
        } catch (const std::runtime_error &e) {
            throw PcbEscapeError(ref + ": " + e.what());
        }
        for (const auto &s : segs)
            for (const auto &[x0, y0, x1, y1, rule, label] : obstacles.at(ref).front) {
                auto d = seg_box_dist(s.ax, s.ay, s.bx, s.by, {x0, y0, x1, y1});
                auto need = s.w / 2 + std::max(.15, rule);
                if (d < need)
                    throw PcbEscapeError(ref + ": ladder " + s.role + " " + point_repr(s.ax, s.ay) +
                                         "-" + point_repr(s.bx, s.by) + " vs foreign " + label +
                                         ": " + f(d, 4) + " < " + f(need, 4));
            }
        ladders[ref] = std::move(segs);
    }
    self_check(m, conns, by_conn, ladders, zone);
    for (auto &[ref, vias] : by_conn) {
        const auto &inst = m.insts[conns.at(ref).index];
        std::stable_sort(vias.begin(), vias.end(), [](const auto &a, const auto &b) {
            return std::tie(a.u, a.v) < std::tie(b.u, b.v);
        });
        for (const auto &v : vias) {
            PcbCheckCopper cu;
            cu.kind = "via";
            auto [x, y] = board(inst, v.u, v.v);
            std::tie(cu.x, cu.y) = round_xy(x, y, 4);
            cu.size = v.dia;
            cu.drill = v.drill;
            cu.net = gn->second;
            cu.net_name = "GND";
            cu.group = "som_escape";
            cu.conn = ref;
            cu.role = v.role;
            out.copper.push_back(cu);
        }
        meta.vias[ref] = static_cast<int>(vias.size());
    }
    for (auto &[ref, segs] : ladders) {
        const auto &inst = m.insts[conns.at(ref).index];
        std::stable_sort(segs.begin(), segs.end(), [](const auto &a, const auto &b) {
            return std::tie(a.role, a.ax, a.ay, a.bx, a.by) <
                   std::tie(b.role, b.ax, b.ay, b.bx, b.by);
        });
        for (const auto &s : segs) {
            PcbCheckCopper cu;
            cu.kind = "segment";
            auto a = board(inst, s.ax, s.ay), b = board(inst, s.bx, s.by);
            std::tie(cu.x1, cu.y1) = round_xy(a.first, a.second, 4);
            std::tie(cu.x2, cu.y2) = round_xy(b.first, b.second, 4);
            cu.width = s.w;
            cu.net = gn->second;
            cu.net_name = "GND";
            cu.group = "som_escape";
            cu.conn = ref;
            cu.role = s.role;
            out.copper.push_back(cu);
        }
    }
    meta.coexistence = coexistence(input, conns, meta.ledger, sorted);
    for (auto &[ref, per] : meta.coverage_mm)
        for (auto &[pad, d] : per) {
            (void)ref;
            (void)pad;
            meta.worst_cover_mm = std::max(meta.worst_cover_mm, d);
            d = py_round(d, 4);
        }
    meta.worst_cover_mm = py_round(meta.worst_cover_mm, 4);
    meta.escape_region = round_box(zone, 4);
    meta.som_interface_sha256 = pcb_sha256(input.interface_bytes());
    return out;
}
} // namespace schgen
