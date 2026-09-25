#include "pcb_escape_internal.hpp"

namespace schgen {
using namespace pcb_escape;
PcbEscapePlanResult build_pcb_escape_plan(const PcbEscapeInput &input) {
    const auto &m = input.model();
    const auto conns = prepare_connectors(m);
    PcbEscapePlanResult plan;
    plan.consumer = "T1 composition legalizer (D13): treat every corridor rect + the som_escape "
                    "via sites as placement constraints";
    for (const auto &[ref, c] : conns) {
        const auto &inst = m.insts[c.index];
        const auto [tip, escape_v] =
            escape_lane_extents(c.contacts.row_v, c.contacts.half_h, lane_handle);
        std::map<int, std::vector<std::tuple<double, std::string, std::string>>> rows;
        int n_netted = 0;
        for (const auto &[pad, net] : inst.pad_nets) {
            auto p = c.pads.find(pad);
            if (net.first <= 0 || p == c.pads.end())
                continue;
            ++n_netted;
            auto [u, v] = p->second;
            int sign = pad_row_sign(v, .5);
            if (sign)
                rows[sign].emplace_back(u, pad, net.second);
        }
        plan.netted_counts[ref] = n_netted;
        auto &lanes = plan.lanes[ref];
        for (auto &[sign, entries] : rows) {
            std::sort(entries.begin(), entries.end());
            int index = 0;
            for (const auto &[u, pad, name] : entries) {
                PcbEscapeLaneRecord ln;
                ln.pad = pad;
                ln.net = name;
                ln.row = sign;
                ln.lane = index++;
                auto klass = pcb_classify_net(name);
                double port_v = 0;
                if (klass == "GND") {
                    ln.direction = "inward";
                    ln.width = .30;
                    ln.si_class = "GND";
                } else if (klass == "POWER") {
                    ln.direction = "plane";
                    port_v = signed_mag(tip + .5, sign);
                    ln.width = .4;
                    ln.si_class = "POWER";
                } else {
                    ln.direction = "outward";
                    port_v = signed_mag(escape_v, sign);
                    auto cls_it = m.netclass_of.find(name);
                    const auto cls = cls_it == m.netclass_of.end() ? "Default" : cls_it->second;
                    auto geo = input.classes().find(cls);
                    bool has = geo != input.classes().end() && geo->second.has_value();
                    if (!has && starts(cls, "DP"))
                        throw PcbEscapeError(ref + "." + pad + " net " + name + ": diff class " +
                                             cls + " has no width geometry (fail loud)");
                    ln.width = has ? geo->second->width_mm : .2032;
                    ln.si_class = input.classify(name).klass;
                }
                auto [px, py] = board(inst, u, port_v);
                std::tie(ln.port_x, ln.port_y) = round_xy(px, py, 4);
                ln.width = py_round(ln.width, 4);
                lanes.push_back(std::move(ln));
            }
        }
        for (int sign : {-1, 1}) {
            PcbEscapeLaneRecord *prev = nullptr;
            for (auto &ln : lanes)
                if (ln.row == sign && ln.direction == "plane") {
                    if (prev && bus_lane_adjacent(prev->net, ln.net, prev->lane, ln.lane)) {
                        auto grp = prev->bus_group.value_or(ref + ":" + prev->net + ":" +
                                                            std::to_string(sign));
                        prev->bus_group = grp;
                        ln.bus_group = grp;
                    }
                    prev = &ln;
                }
        }
        for (const auto &[sign, entries] : rows) {
            double lo = std::get<0>(entries.front()), hi = std::get<0>(entries.back());
            auto a = board(inst, lo - .5, signed_mag(tip, sign));
            auto b = board(inst, hi + .5, signed_mag(escape_v + .3, sign));
            plan.corridors[ref + (sign > 0 ? ":S" : ":N")] = {
                aabb_from_corners(a.first, a.second, b.first, b.second, 4),
                "DF40 escape-lane corridor (T2) — composition legalizer must keep parts + zones "
                "out"};
        }
    }
    std::set<std::string> genuine;
    for (const auto &[ref, c] : conns) {
        std::set<std::string> nets;
        for (const auto &[pad, n] : m.insts[c.index].pad_nets) {
            (void)pad;
            if (!n.second.empty())
                nets.insert(n.second);
        }
        const auto net2base = pcb_hs_pairs(nets);
        std::map<std::string, const PcbEscapeLaneRecord *> lane_of;
        for (const auto &ln : plan.lanes.at(ref))
            lane_of[ln.net] = &ln;
        std::map<std::string, std::vector<std::string>> halves;
        for (const auto &[net, base] : net2base)
            halves[base].push_back(net);
        for (const auto &[base, hs] : halves) {
            std::vector<const PcbEscapeLaneRecord *> recs;
            for (const auto &h : hs)
                if (lane_of.count(h))
                    recs.push_back(lane_of.at(h));
            if (recs.size() != 2)
                continue;
            const PcbEscapeSignalClass *kl = nullptr;
            for (const auto &h : hs) {
                const auto &candidate = input.classify(h);
                if (!kl || candidate.rank() < kl->rank())
                    kl = &candidate;
            }
            const auto &a = *recs[0];
            const auto &b = *recs[1];
            PcbEscapePairRecord rec;
            rec.base = base;
            rec.conn = ref;
            rec.halves = hs;
            rec.si_class = kl->klass;
            rec.same_row = a.row == b.row;
            rec.delta_lane = std::abs(a.lane - b.lane);
            rec.convergence = pair_convergence(rec.same_row, rec.delta_lane);
            plan.pairs.push_back(rec);
            if (rec.si_class == "GENUINE") {
                genuine.insert(base);
                if (!genuine_pair_ok(rec.same_row, rec.delta_lane))
                    throw PcbEscapeError("GENUINE pair " + base + " on " + ref +
                                         ": same_row=" + (rec.same_row ? "True" : "False") +
                                         " delta_lane=" + std::to_string(rec.delta_lane) +
                                         " violates the hard pair terms (measured max |dlane| over "
                                         "the 15 GENUINE pairs = 2)");
            }
        }
    }
    plan.genuine_pairs.assign(genuine.begin(), genuine.end());
    plan.content_key = pcb_escape_content_key(m, input.interface_bytes());
    return plan;
}
} // namespace schgen
