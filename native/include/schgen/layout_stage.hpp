#pragma once

#include "schgen/layout_adapter.hpp"
#include "schgen/layout_sink.hpp"
#include "schgen/layout_arrange.hpp"
#include "schgen/layout_squeeze.hpp"

namespace schgen::layout {

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
    std::string report;
};

std::string squeeze_summary(const SqueezeReport& report);
StageResult squeeze_stage(const PcbPlacementInput& inputs, const PcbModel& model, const PcbEmitPolicy& policy,
                          const AdapterOptions& options);

}
