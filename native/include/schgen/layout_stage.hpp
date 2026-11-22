#pragma once

#include "schgen/layout_adapter.hpp"
#include "schgen/layout_sink.hpp"
#include "schgen/layout_arrange.hpp"
#include "schgen/layout_squeeze.hpp"

namespace schgen::layout {

namespace constants {
inline constexpr NamedConstant widen_steps{"widen_steps", 4, "steps", "policy",
    "outline steps given back on each side, one at a time, while a breach handed over by the placer is repaired"};
inline constexpr std::array stage_registry{widen_steps};
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
};

struct StageResult {
    std::vector<Rebalance> rebalances;
    PcbModel model;
    AttractReport attract, reseat;
    OrderReport order;
    SqueezeReport squeeze;
    BalanceReport balance;
    ArrangeReport arrange;
    bool balanced = false;
    double plain_area = 0, balanced_area = 0;
    std::size_t rear_before = 0, rear_after = 0, faced = 0, unfaced = 0, cleared = 0;
    std::string report, convergence;
    std::vector<RepairRow> repairs;
    std::size_t inherited = 0;
};

std::string squeeze_summary(const SqueezeReport& report);
struct SearchChoice {
    std::array<Side, edge_count> order{Side::east, Side::south, Side::west, Side::north};
    std::size_t plan_skip = 0;
};

void repair_start(Kernel& kernel, const SqueezeOptions& settings, StageResult& result, const std::function<void(bool)>& mark);

StageResult squeeze_stage(const PcbPlacementInput& inputs, const PcbModel& model, const PcbEmitPolicy& policy,
                          const AdapterOptions& options, const SearchChoice& choice = SearchChoice{});

}
