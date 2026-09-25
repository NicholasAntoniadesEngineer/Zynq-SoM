#pragma once
#include "schgen/pcb_escape.hpp"
#include "schgen/pcb_stage_templates.hpp"

namespace schgen {
struct PcbPlacementInput {
    FloorplanInput floorplan;
    // Opaque footprint keys agree with floorplan.footprint_of. These are exact
    // source documents, not posed models. Mirroring stays in memory.
    PcbFootprintPool footprints;
    std::map<std::string, JsonNode> contracts; // all authored, including inert
    KicadNetlist netlist; // independently extracted board schematic connectivity
    SomInterface som_interface;
    std::map<std::string, PcbCheckFootprintPtr> return_path_footprints;
    std::string interface_bytes;
    ProjectStrings function_map;
    JsonNode prior_escape_sidecar; // same snapshot supplies corridors and T2 coexistence
    bool two_side = true;
};
struct PcbZoneResult {
    FloorplanZoneGeometry geometry;
    PcbFootprintPool footprints;
    std::vector<std::string> fallback_events;
    std::map<std::string, std::size_t> quantization_engagements;
};
using PcbPlacementPose = std::tuple<double, double, double, std::string>;
struct PcbPlacementResult {
    PcbModel model;
    FloorplanStage floorplan;
    std::map<std::string, std::map<std::string, PcbPlacementPose>> stages;
    std::vector<std::string> fallback_events;
};
PcbZoneResult build_pcb_zone_geometry(const PcbPlacementInput &);
FloorplanZoneGeometry bind_pcb_zone_shapes(const PcbZoneResult &,
                                           const std::map<std::string, int> &chosen);
// Rebuilds compose terms, metrics, side offers and impedance classes from live
// authored inputs. Caller-supplied prior escape corridors are retained; no
// other precomputed geometry or compose result is reused.
FloorplanInput prepare_pcb_floorplan(const PcbPlacementInput &, const PcbZoneResult &);
// Executes the placed-board stages against an explicitly owned native solve.
// Useful when board generation already owns the physical floorplan result.
PcbPlacementResult place_pcb_model(const PcbPlacementInput &, const PcbZoneResult &,
                                   const FloorplanStage &);
// Production path: derive zones -> native floorplan -> all placement stages ->
// return-path remediation and escape plan. No fixture/model deserialization.
// This constructs a model, not a verification verdict: independent final-model
// placement-contract, placement-flow, compose/coverage and PCB checks remain
// mandatory orchestration steps. Solver feasibility does not replace them.
PcbPlacementResult build_pcb_model(const PcbPlacementInput &);
} // namespace schgen
