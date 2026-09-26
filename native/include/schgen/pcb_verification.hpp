#pragma once
#include "schgen/board_pcb.hpp"
#include "schgen/pcb_placement_gates.hpp"
#include "schgen/ratsnest_gate.hpp"

namespace schgen {
struct PcbVerificationResult {
    bool complete = false;
    RatsnestNets nets;
    RatsnestEdges edges;
    RatsnestGateResult ratsnest;
    PlacementMechResult mechanical;
    ConnectorModelResult connector_models;
    ConnectorSpacingResult connector_spacing;
    RefdesOverlapResult refdes;
    PcbPlacementGatesResult placement;
    PcbFanoutResult fanout;
    ReturnPathResult return_path;
    ReturnStitchResult return_stitch;
    EscapeLaneResult escape_lanes;
    // Fixed SoM contact-level v1 findings and placement coverage/composition
    // stay visible but advisory. Actual carrier return-stitch coverage is hard.
    // This verdict excludes external KiCad DRC and non-PCB board gates.
    bool ok() const;
};
// Caller supplies the independently read emitted board and the persisted
// fanout ceiling. No hidden reads, implicit baseline update or reused verdict.
PcbVerificationResult verify_pcb_geometry(const BoardPcbStage&,
    const PcbEmittedBoard&, std::optional<int> fanout_baseline);
}
