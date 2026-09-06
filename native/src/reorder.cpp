#include "schgen/reorder.hpp"

#include "schgen/occupancy.hpp"
#include "schgen/pack.hpp"
#include "schgen/turn.hpp"

#include <algorithm>
#include <cmath>
#include <map>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace schgen {
namespace {

double py_mod(double value, double modulus) {
    double rem = std::fmod(value, modulus);
    if ((rem < 0.0 && modulus > 0.0) || (rem > 0.0 && modulus < 0.0)) {
        rem += modulus;
    }
    return rem;
}

double group_rot(double rot) {
    return py_mod(py_round(rot, 1), 360.0);
}

struct GroupKey {
    std::string side;
    std::string fp;
    double rot = 0.0;
    bool passive = false;
    bool operator<(const GroupKey& o) const {
        if (side != o.side) {
            return side < o.side;
        }
        if (fp != o.fp) {
            return fp < o.fp;
        }
        if (rot != o.rot) {
            return rot < o.rot;
        }
        return passive < o.passive;
    }
};

std::string rp_key(const std::string& ref, const std::string& pad) {
    std::string out;
    out.reserve(ref.size() + pad.size() + 1);
    out.append(ref);
    out.push_back('\x1f');
    out.append(pad);
    return out;
}

}

std::vector<std::tuple<std::string, std::string, double, bool,
                       std::vector<std::string>>>
group_interchangeable(
    const std::vector<
        std::tuple<std::string, std::string, std::string, double, bool>>&
        rows) {
    std::map<GroupKey, std::vector<std::string>> groups;
    for (const auto& row : rows) {
        GroupKey key;
        key.side = std::get<1>(row);
        key.fp = std::get<2>(row);
        key.rot = group_rot(std::get<3>(row));
        key.passive = std::get<4>(row);
        groups[key].push_back(std::get<0>(row));
    }
    std::vector<std::tuple<std::string, std::string, double, bool,
                           std::vector<std::string>>>
        out;
    out.reserve(groups.size());
    for (auto& item : groups) {
        std::vector<std::string> members = item.second;
        std::sort(members.begin(), members.end());
        out.emplace_back(item.first.side, item.first.fp, item.first.rot,
                         item.first.passive, std::move(members));
    }
    return out;
}

std::tuple<std::vector<ReorderPos>, std::vector<ReorderReport>>
reorder_interchangeable(
    const std::vector<ReorderPos>& pos_in,
    const std::vector<std::tuple<std::string, std::vector<std::string>>>&
        sheets,
    const std::vector<std::string>& skip_sheets,
    const std::vector<std::string>& conn_seated,
    const std::vector<
        std::tuple<std::string, std::string, std::string, double, bool>>&
        members,
    const std::vector<std::tuple<std::string, double, double, double, double>>&
        bboxes,
    const std::vector<std::tuple<std::string, std::vector<std::string>>>&
        pad_names,
    const std::vector<std::tuple<
        std::string, std::vector<std::tuple<std::string, double, double>>>>&
        pad_local,
    const std::vector<std::tuple<std::string, std::string, std::string>>&
        pin_net,
    const std::vector<std::tuple<
        std::string, std::vector<std::pair<std::string, std::string>>>>& nets,
    const std::vector<std::string>& resolvable) {
    std::unordered_map<std::string, std::pair<double, double>> pos;
    pos.reserve(pos_in.size());
    for (const auto& row : pos_in) {
        pos[std::get<0>(row)] = {std::get<1>(row), std::get<2>(row)};
    }
    std::unordered_set<std::string> skip(skip_sheets.begin(),
                                         skip_sheets.end());
    std::unordered_set<std::string> seated(conn_seated.begin(),
                                           conn_seated.end());
    std::unordered_set<std::string> resolv(resolvable.begin(),
                                           resolvable.end());
    std::unordered_map<std::string,
                       std::tuple<std::string, std::string, double, bool>>
        meta;
    meta.reserve(members.size());
    for (const auto& row : members) {
        meta[std::get<0>(row)] = {std::get<1>(row), std::get<2>(row),
                                  std::get<3>(row), std::get<4>(row)};
    }
    std::unordered_map<std::string, Box4> bbox;
    bbox.reserve(bboxes.size());
    for (const auto& row : bboxes) {
        bbox[std::get<0>(row)] = Box4{std::get<1>(row), std::get<2>(row),
                                      std::get<3>(row), std::get<4>(row)};
    }
    std::unordered_map<std::string, std::vector<std::string>> names;
    names.reserve(pad_names.size());
    for (const auto& row : pad_names) {
        names[std::get<0>(row)] = std::get<1>(row);
    }
    std::unordered_map<std::string,
                       std::unordered_map<std::string, std::pair<double, double>>>
        local;
    local.reserve(pad_local.size());
    for (const auto& row : pad_local) {
        auto& dest = local[std::get<0>(row)];
        for (const auto& pad : std::get<1>(row)) {
            dest[std::get<0>(pad)] = {std::get<1>(pad), std::get<2>(pad)};
        }
    }
    std::unordered_map<std::string, std::string> net_of;
    net_of.reserve(pin_net.size());
    for (const auto& row : pin_net) {
        net_of[rp_key(std::get<0>(row), std::get<1>(row))] = std::get<2>(row);
    }
    std::unordered_map<std::string,
                       std::vector<std::pair<std::string, std::string>>>
        net_pins;
    net_pins.reserve(nets.size());
    for (const auto& row : nets) {
        net_pins[std::get<0>(row)] = std::get<1>(row);
    }

    std::vector<std::tuple<std::string, std::vector<std::string>>> sheet_rows =
        sheets;
    std::sort(sheet_rows.begin(), sheet_rows.end(),
              [](const auto& a, const auto& b) {
                  return std::get<0>(a) < std::get<0>(b);
              });

    std::vector<ReorderReport> report;
    for (const auto& sheet_row : sheet_rows) {
        const std::string& sheet = std::get<0>(sheet_row);
        if (skip.find(sheet) != skip.end()) {
            continue;
        }
        std::vector<
            std::tuple<std::string, std::string, std::string, double, bool>>
            rows;
        for (const auto& ref : std::get<1>(sheet_row)) {
            if (pos.find(ref) == pos.end() || resolv.find(ref) == resolv.end()
                || seated.find(ref) != seated.end()) {
                continue;
            }
            auto mit = meta.find(ref);
            if (mit == meta.end()) {
                continue;
            }
            rows.emplace_back(ref, std::get<0>(mit->second),
                              std::get<1>(mit->second),
                              std::get<2>(mit->second),
                              std::get<3>(mit->second));
        }
        const auto groups = group_interchangeable(rows);
        for (const auto& group : groups) {
            const std::vector<std::string>& mems = std::get<4>(group);
            if (mems.size() < 2) {
                continue;
            }
            std::unordered_set<std::string> gset(mems.begin(), mems.end());
            auto bit = bbox.find(mems[0]);
            if (bit == bbox.end()) {
                throw std::runtime_error("reorder_interchangeable: bbox");
            }
            const double rot_key = std::get<2>(group);
            const Box4 eb = turn_box(bit->second, rot_key);
            const double tol_x = std::max(0.6, (eb.x1 - eb.x0) / 2.0);
            const double tol_y = std::max(0.6, (eb.y1 - eb.y0) / 2.0);
            std::vector<std::tuple<std::string, double, double>> grow;
            grow.reserve(mems.size());
            for (const auto& m : mems) {
                auto pit = pos.find(m);
                if (pit == pos.end()) {
                    throw std::runtime_error("reorder_interchangeable: pos");
                }
                grow.emplace_back(m, pit->second.first, pit->second.second);
            }
            const auto clusters =
                cluster_interchangeable_rows(grow, tol_x, tol_y);
            for (const auto& cl : clusters) {
                const std::string& axis = std::get<0>(cl);
                const std::vector<std::string>& cluster = std::get<1>(cl);
                const int ai = axis == "x" ? 0 : 1;
                std::vector<std::string> mlist = cluster;
                std::sort(mlist.begin(), mlist.end());
                std::vector<std::pair<double, double>> slots;
                slots.reserve(cluster.size());
                for (const auto& m : cluster) {
                    auto pit = pos.find(m);
                    if (pit == pos.end()) {
                        throw std::runtime_error(
                            "reorder_interchangeable: slot pos");
                    }
                    slots.push_back(pit->second);
                }
                std::stable_sort(
                    slots.begin(), slots.end(),
                    [ai](const std::pair<double, double>& a,
                         const std::pair<double, double>& b) {
                        const double a0 = ai == 0 ? a.first : a.second;
                        const double a1 = ai == 0 ? a.second : a.first;
                        const double b0 = ai == 0 ? b.first : b.second;
                        const double b1 = ai == 0 ? b.second : b.first;
                        if (a0 != b0) {
                            return a0 < b0;
                        }
                        return a1 < b1;
                    });
                std::vector<std::tuple<
                    std::string, std::vector<std::pair<double, double>>>>
                    static_rows;
                std::unordered_set<std::string> seen_net;
                for (const auto& m : mlist) {
                    auto nit = names.find(m);
                    if (nit == names.end()) {
                        continue;
                    }
                    for (const auto& pad : nit->second) {
                        auto eit = net_of.find(rp_key(m, pad));
                        const std::string& n =
                            eit == net_of.end() ? "" : eit->second;
                        if (n.empty() || seen_net.find(n) != seen_net.end()
                            || net_pins.find(n) == net_pins.end()) {
                            continue;
                        }
                        seen_net.insert(n);
                        std::vector<std::pair<double, double>> pts;
                        for (const auto& pr : net_pins[n]) {
                            const std::string& pref = pr.first;
                            if (gset.find(pref) != gset.end()
                                || (!pref.empty() && pref[0] == '#')
                                || pos.find(pref) == pos.end()
                                || resolv.find(pref) == resolv.end()) {
                                continue;
                            }
                            auto lit = local.find(pref);
                            if (lit == local.end()) {
                                continue;
                            }
                            auto oit = lit->second.find(pr.second);
                            if (oit == lit->second.end()) {
                                continue;
                            }
                            const auto& pp = pos[pref];
                            pts.emplace_back(oit->second.first + pp.first,
                                             oit->second.second + pp.second);
                        }
                        static_rows.emplace_back(n, std::move(pts));
                    }
                }
                std::vector<std::string> order0 = cluster;
                std::stable_sort(
                    order0.begin(), order0.end(),
                    [&pos, ai](const std::string& a, const std::string& b) {
                        const auto& pa = pos.at(a);
                        const auto& pb = pos.at(b);
                        const double a0 = ai == 0 ? pa.first : pa.second;
                        const double b0 = ai == 0 ? pb.first : pb.second;
                        if (a0 != b0) {
                            return a0 < b0;
                        }
                        return a < b;
                    });
                std::unordered_map<std::string, int> assign_map;
                assign_map.reserve(order0.size());
                for (std::size_t i = 0; i < order0.size(); ++i) {
                    assign_map[order0[i]] = static_cast<int>(i);
                }
                std::vector<std::vector<std::vector<Seg2>>> segs_xy;
                segs_xy.reserve(mlist.size());
                for (const auto& m : mlist) {
                    std::vector<std::string> pads;
                    auto lit = local.find(m);
                    if (lit != local.end()) {
                        pads.reserve(lit->second.size());
                        for (const auto& item : lit->second) {
                            pads.push_back(item.first);
                        }
                    }
                    std::sort(pads.begin(), pads.end());
                    std::vector<std::tuple<std::string, double, double>>
                        pad_offs;
                    std::vector<std::string> pad_nets;
                    pad_offs.reserve(pads.size());
                    pad_nets.reserve(pads.size());
                    for (const auto& pad : pads) {
                        const auto& off = local[m][pad];
                        pad_offs.emplace_back(pad, off.first, off.second);
                        auto eit = net_of.find(rp_key(m, pad));
                        pad_nets.push_back(eit == net_of.end() ? ""
                                                               : eit->second);
                    }
                    segs_xy.push_back(cluster_slot_segs(
                        pad_offs, pad_nets, slots, static_rows));
                }
                std::vector<int> init;
                init.reserve(mlist.size());
                for (const auto& m : mlist) {
                    auto ait = assign_map.find(m);
                    if (ait == assign_map.end()) {
                        throw std::runtime_error(
                            "reorder_interchangeable: assign");
                    }
                    init.push_back(ait->second);
                }
                const ReorderAssign hit =
                    reorder_cluster_assign(segs_xy, init, 6);
                if (hit.best == hit.before) {
                    continue;
                }
                if (hit.assign.size() != mlist.size()
                    || slots.size() != mlist.size()) {
                    throw std::runtime_error(
                        "reorder_interchangeable: assign size");
                }
                for (std::size_t i = 0; i < mlist.size(); ++i) {
                    const int slot = hit.assign[i];
                    if (slot < 0
                        || static_cast<std::size_t>(slot) >= slots.size()) {
                        throw std::runtime_error(
                            "reorder_interchangeable: slot");
                    }
                    pos[mlist[i]] = slots[static_cast<std::size_t>(slot)];
                }
                report.emplace_back(
                    sheet,
                    axis + "-" + std::to_string(cluster.size()),
                    hit.before, hit.best);
            }
        }
    }

    std::vector<ReorderPos> pos_out;
    pos_out.reserve(pos.size());
    for (const auto& row : pos_in) {
        const std::string& ref = std::get<0>(row);
        auto pit = pos.find(ref);
        if (pit == pos.end()) {
            pos_out.push_back(row);
        } else {
            pos_out.emplace_back(ref, pit->second.first, pit->second.second);
        }
    }
    return {std::move(pos_out), std::move(report)};
}

}
