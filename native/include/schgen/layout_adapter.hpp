#pragma once

#include "schgen/layout_problem.hpp"
#include "schgen/pcb_emit.hpp"
#include "schgen/pcb_model.hpp"

#include <array>

namespace schgen::layout {

namespace constants {
inline constexpr NamedConstant core_tolerance{"core_tolerance", 0.5, "mm2", "policy",
    "the mechanical gate ignores module-core overlaps up to this area"};
inline constexpr NamedConstant fanout_floor{"fanout_floor", 3.0, "pins", "policy",
    "the fan-out gate judges only parts with at least this many pins"};
inline constexpr NamedConstant relief_reach{"relief_reach", 1.0, "mm", "physical",
    "thermal gap 0.5 plus bridge width 0.5 that the emitter writes for every zone"};
inline constexpr std::array adapter_registry{core_tolerance, fanout_floor, relief_reach};
}

struct AdapterOptions {
    std::string plane_net;
    double edge_clearance = 0;
};

struct ModelBinding {
    Problem problem;
    Placement placement;
    std::vector<std::array<PcbCheckFootprintPtr, 2>> documents;
    std::vector<bool> mirrors_bottom;
};

ModelBinding bind_model(const PcbModel& model, const PcbEmitPolicy& policy, const AdapterOptions& options);
double project_edge_clearance(const JsonNode& project_file);
PcbModel model_with(const PcbModel& base, const ModelBinding& binding, const Placement& placement);

}
