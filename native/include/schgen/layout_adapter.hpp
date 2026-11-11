#pragma once

#include "schgen/layout_problem.hpp"
#include "schgen/pcb_emit.hpp"
#include "schgen/pcb_placement_gates.hpp"
#include "schgen/pcb_model.hpp"

#include <array>

namespace schgen::layout {

namespace constants {
inline constexpr NamedConstant core_tolerance{"core_tolerance", 0.5, "mm2", "policy",
    "the mechanical gate ignores module-core overlaps up to this area"};
inline constexpr NamedConstant fanout_floor{"fanout_floor", 3.0, "pins", "policy",
    "the fan-out gate judges only parts with at least this many connected nets"};
inline constexpr NamedConstant relief_reach{"relief_reach", 1.0, "mm", "physical",
    "thermal gap 0.5 plus bridge width 0.5 that the emitter writes for every zone"};
inline constexpr NamedConstant edge_reach{"edge_reach", 0.6, "mm", "policy",
    "the mechanical gate accepts a connector whose courtyard is within this distance of its edge"};
inline constexpr NamedConstant connector_overlap{"connector_overlap", 0.05, "mm", "policy",
    "the connector-spacing gate tolerates this much overlap of connector pad extents"};
inline constexpr NamedConstant band_share{"band_share", 0.5, "ratio", "policy",
    "the connector-spacing gate treats two connectors as sharing an edge at this overlap share"};
inline constexpr NamedConstant overmold_gap{"overmold_gap", 18.0, "mm", "physical",
    "clear gap the connector-spacing gate requires between two overmolded plugs"};
inline constexpr NamedConstant boot_gap{"boot_gap", 3.0, "mm", "physical",
    "gap the connector-spacing gate requires between an overmolded plug and a plain neighbour"};
inline constexpr NamedConstant compare_guard{"compare_guard", 1.0, "nm", "policy",
    "slack demanded of a moved part so floating-point gate comparisons cannot disagree at the limit"};
inline constexpr NamedConstant group_guard{"group_guard", 200.0, "nm", "policy",
    "slack for subsystem distances, which the flow gate rounds to four decimals"};
inline constexpr NamedConstant owner_reach{"owner_reach", 3.0, "mm", "policy",
    "preferred distance from an owned two-pin part to the pin it serves; a soft preference, never a hard rule"};
inline constexpr NamedConstant hole_inset{"hole_inset", 5.0, "mm", "policy",
    "distance of a corner mounting hole from both edges of its corner, before the fixed-part grid"};
inline constexpr NamedConstant mark_inset{"mark_inset", 9.0, "mm", "policy",
    "distance of a corner fiducial from both edges of its corner"};
inline constexpr NamedConstant escape_tie{"escape_tie", 2e-3, "mm", "policy",
    "tie width when choosing a pad's nearest courtyard side; twice the gate's, so the kernel never rings fewer sides"};
inline constexpr NamedConstant area_guard{"area_guard", 1e-6, "mm2", "policy",
    "slack demanded of a module-core overlap so the mechanical gate's floating-point area cannot disagree at the limit"};
inline constexpr std::array adapter_registry{core_tolerance, fanout_floor, relief_reach, edge_reach, owner_reach,
                                             connector_overlap, band_share, overmold_gap, boot_gap,
                                             compare_guard, group_guard, hole_inset, mark_inset, area_guard,
                                             escape_tie};
}

struct AdapterOptions {
    std::string plane_net;
    double edge_clearance = 0;
    std::vector<std::string> overmold_parts;
    double edge_setback = 0;
};

struct ModelBinding {
    Problem problem;
    Placement placement;
    std::vector<std::array<PcbCheckFootprintPtr, 2>> documents;
    std::vector<bool> mirrors_bottom;
};

ModelBinding bind_model(const PcbModel& model, const PcbEmitPolicy& policy, const PcbPlacementGatePolicy* gates,
                        const AdapterOptions& options);
double project_edge_clearance(const JsonNode& project_file);
PcbModel model_with(const PcbModel& base, const ModelBinding& binding, const Placement& placement);
PcbModel model_with(const PcbModel& base, const ModelBinding& binding, const Placement& placement,
                    const Board& board);

struct GateVerdict {
    bool fanout = false, mechanical = false, on_board = false, grouped = false, contracts = false, spacing = false;
    bool ok() const { return fanout && mechanical && on_board && grouped && contracts && spacing; }
    std::string text() const;
};

GateVerdict judge_model(const PcbPlacementInput& inputs, const PcbModel& model);

}
