#include "schgen/pack_anchor.hpp"

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <tuple>

namespace schgen {

std::pair<double, double> zone_anchor(char zone, double som_x, double som_y,
                                      double som_w, double som_h,
                                      double board_w, double board_h) {
    switch (zone) {
        case 'N':
            return {som_x + som_w / 2.0, som_y / 2.0};
        case 'S':
            return {som_x + som_w / 2.0,
                    (som_y + som_h + board_h) / 2.0};
        case 'W':
            return {som_x / 2.0, som_y + som_h / 2.0};
        case 'E':
            return {(som_x + som_w + board_w) / 2.0, board_h / 2.0};
        default:
            throw std::runtime_error("zone_anchor: zone required");
    }
}

std::pair<double, double> pack_anchor(const PackAnchorIn& in) {
    if (in.face_override) {
        switch (in.face) {
            case 'E':
                return {in.som_x + in.som_w + in.som_halo + in.block_w / 2.0,
                        in.som_y + in.som_h / 2.0};
            case 'W':
                return {in.som_x - in.som_halo - in.block_w / 2.0,
                        in.som_y + in.som_h / 2.0};
            case 'N':
                return {in.som_x + in.som_w / 2.0,
                        in.som_y - in.som_halo - in.block_h / 2.0};
            case 'S':
                return {in.som_x + in.som_w / 2.0,
                        in.som_y + in.som_h + in.som_halo + in.block_h / 2.0};
            default:
                throw std::runtime_error("pack_anchor: face required");
        }
    }

    double zone_ax = in.zone_ax;
    double zone_ay = in.zone_ay;
    double zone_weight = 0.0;
    double som_weight = 0.0;
    if (in.exclusive && in.zone_is_at_edge) {
        zone_weight = in.pull_weight;
        som_weight = 0.0;
        if (in.inboard) {
            switch (in.edge) {
                case 'N':
                    zone_ax = in.eb_cx;
                    zone_ay = in.eb_y + in.eb_h + in.block_h / 2.0;
                    break;
                case 'S':
                    zone_ax = in.eb_cx;
                    zone_ay = in.eb_y - in.block_h / 2.0;
                    break;
                case 'W':
                    zone_ax = in.eb_x + in.eb_w + in.block_w / 2.0;
                    zone_ay = in.eb_cy;
                    break;
                case 'E':
                    zone_ax = in.eb_x - in.block_w / 2.0;
                    zone_ay = in.eb_cy;
                    break;
                default:
                    throw std::runtime_error("pack_anchor: edge required");
            }
        }
    } else {
        zone_weight = in.zone_w;
        som_weight = in.som_w_scale * std::max(in.som_pull, 0.0);
    }

    double weight_sum = zone_weight + som_weight;
    double anchor_x = zone_weight * zone_ax + som_weight * in.som_cx;
    double anchor_y = zone_weight * zone_ay + som_weight * in.som_cy;
    if (in.has_soft_pull) {
        anchor_x += in.pull_weight * in.pull_x;
        anchor_y += in.pull_weight * in.pull_y;
        weight_sum += in.pull_weight;
    }
    for (const auto& neighbor : in.affinity) {
        const double neighbor_cx = std::get<0>(neighbor);
        const double neighbor_cy = std::get<1>(neighbor);
        const double raw_weight = std::get<2>(neighbor);
        const double powered_weight = std::pow(raw_weight, in.aff_pow);
        anchor_x += powered_weight * neighbor_cx;
        anchor_y += powered_weight * neighbor_cy;
        weight_sum += powered_weight;
    }
    if (weight_sum == 0.0) {
        throw std::runtime_error("pack_anchor: weight sum required");
    }
    return {anchor_x / weight_sum, anchor_y / weight_sum};
}

}  // namespace schgen
