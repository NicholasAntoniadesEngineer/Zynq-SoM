#pragma once
#include "schgen/pcb_placement.hpp"
#include "schgen/footprint_pads.hpp"

namespace schgen {
struct BoardInputOptions {
    FootprintResolutionOptions footprints;
    std::optional<std::filesystem::path> som_pcb, floorplan_spec;
    std::optional<FloorplanPoint> module_offset;
    double place_clear = 0.5;
    bool two_side = true;
    std::shared_ptr<const FloorplanExperiment> experiment;
};
// Read current project/design/library inputs once. The caller supplies a real
// extracted board netlist and validated link result; neither is synthesized
// from fixture geometry or a previously placed board. No files are written.
PcbPlacementInput load_board_inputs(const ProjectPaths&,
    const std::vector<ProjectCircuit>&, const LinkResult&, const KicadNetlist&,
    const BoardInputOptions& = {});
}
