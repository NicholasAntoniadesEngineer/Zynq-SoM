#pragma once
#include "schgen/pcb_checks.hpp"
#include "schgen/ratsnest.hpp"

namespace schgen {
inline constexpr double ratsnest_dispersion_max = 9.0;
inline constexpr int ratsnest_small_n = 3;
struct RatsnestGateResult {
    bool ok = true;
    std::vector<std::string> off_board, dispersed;
    std::vector<std::tuple<std::string, int, double, double>> clusters;
    double cross_mm = 0, total_mm = 0, cross_budget_mm = 0, board_w = 0, board_h = 0;
    int n_cross = 0, n_subsystems = 0;
    double cross_ratio() const { return total_mm ? cross_mm / total_mm : 0; }
    bool cross_ok() const { return cross_mm <= cross_budget_mm; }
    std::string summary() const;
};
RatsnestNets ratsnest_net_pad_positions(const PcbCheckModel&);
RatsnestGateResult check_ratsnest(const PcbCheckInput&, const RatsnestNets* = nullptr,
    const RatsnestEdges* = nullptr, double cross_k = default_engine_config.cross_k);
std::map<std::string, double> ratsnest_dispersion_by_sheet(const RatsnestGateResult&);
} // namespace schgen
