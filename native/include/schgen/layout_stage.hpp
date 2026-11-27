#pragma once

#include "schgen/layout_construct.hpp"
#include "schgen/layout_adapter.hpp"
#include "schgen/layout_sink.hpp"
#include "schgen/layout_arrange.hpp"
#include "schgen/layout_squeeze.hpp"

namespace schgen::layout {

namespace constants {
inline constexpr NamedConstant widen_steps{"widen_steps", 4, "steps", "policy",
    "outline steps given back on each side, one at a time, while a breach handed over by the placer is repaired"};
inline constexpr NamedConstant spread_rounds{"spread_rounds", 24, "rounds", "policy",
    "times the outline is opened by the widest density gap on every side, each followed by moving the crowded clusters apart, before the gaps a density below the densest asks for are reported as impossible"};
inline constexpr NamedConstant tap_evictions{"tap_evictions", 256, "seats", "policy",
    "seats at which a test point may move small neighbours aside to reach its net; a test point is one small pad, so more seats are worth trying than for a part with its own rules"};
inline constexpr std::array stage_registry{widen_steps, spread_rounds, tap_evictions};
}

struct RepairRow {
    std::string level, rule, subject, action;
    std::size_t before = 0, after = 0;
    bool kept = false;
};

struct StageOptions {
    std::string plane_net;
    std::vector<std::string> overmold_parts;
};

struct Rebalance {
    BalanceReport balance;
    double before = 0, after = 0;
    bool kept = false;
    BalanceScope scope = BalanceScope::mirrored;
};

struct BalanceTrial {
    BalanceScope scope = BalanceScope::mirrored;
    BalanceReport balance;
    double area = 0;
    bool squeezed = false, kept = false;
};

struct SpreadReport {
    Board before, after;
    std::size_t rounds = 0, moved = 0, closed_before = 0, closed_after = 0;
    Nm widest = 0;
};

struct StageResult {
    std::optional<ConstructReport> construct;
    std::vector<Rebalance> rebalances;
    std::vector<BalanceTrial> trials;
    std::vector<std::pair<double, std::string>> left_on_top;
    PcbModel model;
    AttractReport attract, reseat;
    OrderReport order;
    SqueezeReport squeeze;
    BalanceReport balance;
    ArrangeReport arrange;
    bool balanced = false;
    double plain_area = 0, balanced_area = 0;
    std::size_t rear_before = 0, rear_after = 0, faced = 0, unfaced = 0, cleared = 0;
    std::string report, convergence, density;
    SpreadReport spread;
    std::vector<RepairRow> repairs;
    std::size_t inherited = 0;
};

std::string squeeze_summary(const SqueezeReport& report);
struct SearchChoice {
    std::array<Side, edge_count> order{Side::east, Side::south, Side::west, Side::north};
    std::size_t plan_skip = 0;
};

void open_spacing(Kernel& kernel, const SqueezeOptions& settings, SpreadReport& report);
void repair_start(Kernel& kernel, const SqueezeOptions& settings, StageResult& result, const std::function<void(bool)>& mark);
std::size_t start_debt(const Kernel& kernel);

StageResult squeeze_stage(const PcbPlacementInput& inputs, const PcbModel& model, const PcbEmitPolicy& policy,
                          const AdapterOptions& options, const SearchChoice& choice = SearchChoice{});

}
