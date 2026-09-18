#include "schgen/ratsnest.hpp"
#include "schgen/legalize.hpp"
#include "schgen/occupancy.hpp"
#include "schgen/pack.hpp"

#include <stdexcept>

namespace schgen {
RatsnestEdges ratsnest_mst(const RatsnestNets& nets) {
    RatsnestEdges result;
    std::vector<std::pair<double, double>> xy;
    for (const auto& [name, pads] : nets) {
        xy.clear();
        xy.reserve(pads.size());
        for (const auto& pad : pads) xy.emplace_back(std::get<0>(pad), std::get<1>(pad));
        result.emplace(name, mst_manhattan(xy));
    }
    return result;
}

std::tuple<double, double, int> ratsnest_lengths(
    const RatsnestNets& nets, const RatsnestEdges& edges) {
    double cross = 0.0, total = 0.0;
    int count = 0;
    for (const auto& [name, pads] : nets) {
        const auto found = edges.find(name);
        if (found == edges.end()) throw std::runtime_error("ratsnest: missing net " + name);
        for (const auto& [a, b] : found->second) {
            if (a < 0 || b < 0 || static_cast<std::size_t>(a) >= pads.size()
                || static_cast<std::size_t>(b) >= pads.size()) {
                throw std::runtime_error("ratsnest: invalid edge in " + name);
            }
            const auto& pa = pads[static_cast<std::size_t>(a)];
            const auto& pb = pads[static_cast<std::size_t>(b)];
            const double d = hypot_xy(std::get<0>(pa), std::get<1>(pa),
                                      std::get<0>(pb), std::get<1>(pb));
            total += d;
            if (std::get<3>(pa) != std::get<3>(pb)) { cross += d; ++count; }
        }
    }
    return {py_round(cross, 1), py_round(total, 1), count};
}
}
