#pragma once
#include "schgen/board_inputs.hpp"
#include "schgen/netlist_gate.hpp"
#include "schgen/pcb_emit.hpp"

namespace schgen {
// Validate complete connected-pin partitions against live authored circuits.
// Internal net names may change; public rail/port identities may not.
void validate_board_input_connectivity(const std::vector<ProjectCircuit>&,
    const SheetIndex&, const KicadNetlist&);
struct BoardPcbStage {
    std::vector<ProjectCircuit> circuits;
    PcbPlacementInput inputs;
    PcbPlacementResult placement;
    PcbEmissionResult emission;
};
// Complete live construction, not an aggregate verification verdict. No cached
// netlist or placed-board input; callers must apply independent final gates.
// An explicit schematic supports freshly authored isolated builds; omission
// retains the project-root schematic. The supplied file is always extracted.
BoardPcbStage prepare_board_pcb(const ProjectPaths&,
    const NetlistExtractOptions& = {}, const BoardInputOptions& = {},
    const std::filesystem::path& schematic = {});
// Explicit destination; project configuration is read from the destination to
// preserve caller settings. Files are individually atomically replaced.
void publish_board_pcb(const BoardPcbStage&, const std::filesystem::path&,
                       QuantizationCounts* = nullptr);
}
