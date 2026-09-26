#pragma once
#include "schgen/board_inputs.hpp"
#include "schgen/netlist_gate.hpp"
#include "schgen/pcb_emit.hpp"

namespace schgen {
struct BoardPcbStage {
    std::vector<ProjectCircuit> circuits;
    PcbPlacementInput inputs;
    PcbPlacementResult placement;
    PcbEmissionResult emission;
};
// Complete live construction, not an aggregate verification verdict. No cached
// netlist or placed-board input; callers must apply independent final gates.
BoardPcbStage prepare_board_pcb(const ProjectPaths&,
    const NetlistExtractOptions& = {}, const BoardInputOptions& = {});
// Explicit destination; project configuration is read from the destination to
// preserve caller settings. Files are individually atomically replaced.
void publish_board_pcb(const BoardPcbStage&, const std::filesystem::path&);
}
