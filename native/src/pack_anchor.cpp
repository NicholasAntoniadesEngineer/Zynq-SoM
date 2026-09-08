#include "schgen/pack_anchor.hpp"

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

#include <algorithm>
#include <cctype>
#include <cmath>
#include <stdexcept>
#include <string>
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

std::string j_edge_of(double connector_x, double connector_y, double som_w,
                      double som_h) {
    struct Candidate {
        double distance;
        const char* edge;
    };
    const Candidate candidates[4] = {
        {connector_y, "N"},
        {som_h - connector_y, "S"},
        {connector_x, "W"},
        {som_w - connector_x, "E"},
    };
    const Candidate* best = &candidates[0];
    for (int i = 1; i < 4; ++i) {
        const Candidate& row = candidates[i];
        if (row.distance < best->distance
            || (row.distance == best->distance
                && std::string(row.edge) < std::string(best->edge))) {
            best = &row;
        }
    }
    return best->edge;
}

std::vector<std::pair<std::string, std::string>> j_edge_map(
    const std::vector<std::tuple<std::string, double, double>>& connectors,
    double som_w, double som_h) {
    std::vector<std::pair<std::string, std::string>> out;
    out.reserve(connectors.size());
    for (const auto& row : connectors) {
        out.emplace_back(std::get<0>(row),
                         j_edge_of(std::get<1>(row), std::get<2>(row), som_w,
                                   som_h));
    }
    return out;
}

std::optional<std::string> dominant_j(
    const std::vector<std::pair<std::string, int>>& affinity) {
    if (affinity.empty()) {
        return std::nullopt;
    }
    std::pair<std::string, int> best = affinity.front();
    for (const auto& row : affinity) {
        if (row.second > best.second
            || (row.second == best.second && row.first < best.first)) {
            best = row;
        }
    }
    return best.first;
}

namespace {

bool is_alnum_char(char value) {
    return std::isalnum(static_cast<unsigned char>(value)) != 0;
}

}  // namespace

std::vector<std::string> affinity_j_from_expect(const std::string& expect) {
    std::vector<std::string> out;
    for (std::size_t i = 0; i < expect.size(); ++i) {
        const char mark = expect[i];
        if (mark != 'j' && mark != 'J') {
            continue;
        }
        if (i + 1 >= expect.size()) {
            continue;
        }
        const char digit = expect[i + 1];
        if (digit != '1' && digit != '2' && digit != '3') {
            continue;
        }
        if (i > 0 && is_alnum_char(expect[i - 1])) {
            continue;
        }
        if (i + 2 < expect.size() && is_alnum_char(expect[i + 2])) {
            continue;
        }
        out.push_back(std::string("J") + digit);
    }
    return out;
}

std::optional<std::string> affinity_j_from_target(const std::string& target) {
    const std::string sheet_prefix = "sheet som_j";
    if (target.size() >= sheet_prefix.size()
        && target.compare(0, sheet_prefix.size(), sheet_prefix) == 0) {
        const auto first_space = target.find(' ');
        if (first_space == std::string::npos
            || first_space + 1 >= target.size()) {
            throw std::runtime_error(
                "affinity_j_from_target: sheet token required");
        }
        const auto second_space = target.find(' ', first_space + 1);
        const std::string token = target.substr(
            first_space + 1,
            second_space == std::string::npos
                ? std::string::npos
                : second_space - first_space - 1);
        const std::string som_j = "som_j";
        std::string rest = token.size() >= som_j.size()
                               ? token.substr(som_j.size())
                               : token;
        const auto colon = rest.find(':');
        if (colon != std::string::npos) {
            rest = rest.substr(0, colon);
        }
        const std::string name = "J" + rest;
        if (name == "J1" || name == "J2" || name == "J3") {
            return name;
        }
        return std::nullopt;
    }
    const std::string som_prefix = "SoM ";
    if (target.size() >= som_prefix.size()
        && target.compare(0, som_prefix.size(), som_prefix) == 0) {
        const auto open = target.find("(J");
        if (open == std::string::npos || open + 3 > target.size()) {
            return std::nullopt;
        }
        const std::string name = target.substr(open + 1, 2);
        if (name == "J1" || name == "J2" || name == "J3") {
            return name;
        }
    }
    return std::nullopt;
}

std::vector<std::pair<std::string, std::vector<std::pair<std::string, int>>>>
j_affinity(
    const std::vector<std::string>& sheets,
    const std::vector<std::tuple<std::string, bool, std::string,
                                 std::vector<std::string>>>& bindings) {
    std::vector<std::pair<std::string, std::vector<std::pair<std::string, int>>>>
        out;
    out.reserve(sheets.size());
    for (const auto& name : sheets) {
        out.emplace_back(name, std::vector<std::pair<std::string, int>>{});
    }
    auto counts_of = [&](const std::string& sheet)
        -> std::vector<std::pair<std::string, int>>& {
        for (auto& row : out) {
            if (row.first == sheet) {
                return row.second;
            }
        }
        out.emplace_back(sheet, std::vector<std::pair<std::string, int>>{});
        return out.back().second;
    };
    auto bump = [](std::vector<std::pair<std::string, int>>& counts,
                   const std::string& jack) {
        for (auto& row : counts) {
            if (row.first == jack) {
                row.second += 1;
                return;
            }
        }
        counts.emplace_back(jack, 1);
    };
    for (const auto& binding : bindings) {
        const std::string& sheet = std::get<0>(binding);
        const bool deferred = std::get<1>(binding);
        const std::string& expect = std::get<2>(binding);
        const auto& targets = std::get<3>(binding);
        auto& counts = counts_of(sheet);
        if (deferred) {
            if (expect.empty()) {
                throw std::runtime_error(
                    "j_affinity: deferred expect required");
            }
            for (const auto& jack : affinity_j_from_expect(expect)) {
                bump(counts, jack);
            }
            continue;
        }
        for (const auto& target : targets) {
            const auto jack = affinity_j_from_target(target);
            if (jack.has_value()) {
                bump(counts, *jack);
            }
        }
    }
    return out;
}

}  // namespace schgen
